import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.story import GeneratedScene, StoryGenerationRequest, StoryGenerationResponse
from app.services.imagekit_uploader import ImageKitUploader
from app.services.media_validation import MediaValidationError
from app.services.narration_builder import NarrationBuilder
from app.services.narration_service import NarrationGenerationError, NarrationService
from app.services.notebooklm_service import NotebookLMGenerationError, NotebookLMService
from app.services.prompt_builder import PromptBuilder
from app.services.slide_extractor import SlideExtractor
from app.services.story_repository import StoryRepository
from app.services.video_composer import VideoComposer, VideoCompositionError


logger = logging.getLogger(__name__)
router = APIRouter()

prompt_builder = PromptBuilder()
slide_extractor = SlideExtractor()
narration_builder = NarrationBuilder()
narration_service = NarrationService()
video_composer = VideoComposer()
imagekit_uploader = ImageKitUploader()
story_repository = StoryRepository()


def _arabic_failure(exc: Exception) -> str:
    if isinstance(exc, NotebookLMGenerationError):
        return exc.user_message
    if isinstance(exc, NarrationGenerationError):
        return exc.user_message
    if isinstance(exc, (VideoCompositionError, MediaValidationError)):
        return "تعذر إنشاء فيديو صالح بالصوت والصورة. يرجى إعادة المحاولة."
    if isinstance(exc, TimeoutError):
        return "انتهت مهلة إنشاء القصة. يرجى إعادة المحاولة."
    return "تعذر إكمال إنشاء القصة. يرجى إعادة المحاولة."


def _texts_for_unique_slides(all_texts: list[str], slide_images: list[str]) -> list[str]:
    result: list[str] = []
    for image_path in slide_images:
        try:
            page_number = int(Path(image_path).stem.rsplit("_", 1)[1])
            result.append(all_texts[page_number - 1] if page_number <= len(all_texts) else "")
        except (IndexError, ValueError):
            result.append("")
    return result


@router.post("/generate-story", response_model=StoryGenerationResponse)
async def generate_story(req: StoryGenerationRequest):
    story_id = req.story_id or str(uuid.uuid4())
    work_dir = os.path.join(settings.TEMP_DIR, story_id)
    os.makedirs(work_dir, exist_ok=True)
    logger.info("[Sard][%s] Generation started: title=%s", story_id, req.story_title)

    try:
        story_md_path = os.path.join(work_dir, "story.md")
        Path(story_md_path).write_text(
            prompt_builder.build_story_markdown(req),
            encoding="utf-8",
        )

        presentation_path = ""
        slide_images: list[str] = []
        slide_texts: list[str] = []
        total_attempts = settings.GENERATION_RETRY_LIMIT + 1
        for attempt in range(total_attempts):
            retrying = attempt > 0
            attempt_dir = os.path.join(work_dir, f"notebooklm_attempt_{attempt + 1}")
            slides_dir = os.path.join(work_dir, f"slides_attempt_{attempt + 1}")
            prompt = prompt_builder.build_notebooklm_prompt(req, expansion_retry=retrying)
            notebooklm = NotebookLMService()
            presentation_path = await notebooklm.run_pipeline(story_md_path, prompt, attempt_dir)
            slide_images = await slide_extractor.extract_slides(presentation_path, slides_dir)
            all_texts = slide_extractor.extract_slide_texts(presentation_path)
            slide_texts = _texts_for_unique_slides(all_texts, slide_images)
            logger.info(
                "[Sard][%s] NotebookLM generated %s unique slides (attempt %s/%s)",
                story_id,
                len(slide_images),
                attempt + 1,
                total_attempts,
            )
            if len(slide_images) >= settings.MIN_SLIDES:
                break
            logger.warning(
                "[Sard][%s] Insufficient NotebookLM slides: got=%s required=%s",
                story_id,
                len(slide_images),
                settings.MIN_SLIDES,
            )

        if len(slide_images) < settings.MIN_SLIDES:
            raise NotebookLMGenerationError(
                f"NotebookLM returned {len(slide_images)} unique slides after controlled retry"
            )

        slides = narration_builder.build(req, slide_images, slide_texts)
        audio_dir = os.path.join(work_dir, "narration_segments")
        os.makedirs(audio_dir, exist_ok=True)
        for slide in slides:
            slide.audio_path = os.path.join(audio_dir, f"scene_{slide.index:02d}.mp3")
            await narration_service.generate_narration(
                text=slide.narration_text,
                voice_gender=req.narrator_gender,
                voice_tone=req.voice_tone,
                output_path=slide.audio_path,
            )
            audio_info = narration_service.validate(slide.audio_path)
            slide.audio_duration = audio_info.duration
            logger.info(
                "[Sard][%s] Narration generated for slide %s: %.2fs",
                story_id,
                slide.index,
                slide.audio_duration,
            )

        narration_path = os.path.join(work_dir, "narration.mp3")
        video_dir = os.path.join(work_dir, "video")
        video_path, thumbnail_path, duration_seconds = await video_composer.compose_video(
            slides=slides,
            output_dir=video_dir,
            narration_output_path=narration_path,
        )

        uploaded_urls = await imagekit_uploader.upload_assets(
            presentation_path=presentation_path,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            story_id=story_id,
            narration_path=narration_path,
        )
        created_at = datetime.now(timezone.utc).isoformat()
        narration_url = uploaded_urls.get("narration_audio_url") or (
            f"http://127.0.0.1:8000/temp/{story_id}/narration.mp3"
        )
        scenes = [
            GeneratedScene(
                scene_number=slide.index,
                title=slide.title,
                visual_description=f"مادة بصرية تعليمية مولدة عبر NotebookLM حول {req.story_title}",
                narration_text=slide.narration_text,
                image_url=f"http://127.0.0.1:8000/temp/{story_id}/{os.path.relpath(slide.visual_path, work_dir).replace(os.sep, '/')}",
                duration_seconds=slide.display_duration,
            )
            for slide in slides
        ]
        record = {
            "story_id": story_id,
            "user_id": "anonymous_user",
            "original_inputs": req.model_dump(),
            "notebooklm_prompt": prompt_builder.build_notebooklm_prompt(req),
            "presentation_url": uploaded_urls.get("presentation_url"),
            "video_url": uploaded_urls.get("video_url"),
            "thumbnail_url": uploaded_urls.get("thumbnail_url"),
            "narration_audio_url": narration_url,
            "duration_seconds": duration_seconds,
            "scenes": [scene.model_dump() for scene in scenes],
            "created_at": created_at,
            "status": "completed",
        }
        story_repository.save_story_record(record)
        logger.info(
            "[Sard][%s] Generation completed: slides=%s duration=%.2fs",
            story_id,
            len(slides),
            duration_seconds,
        )
        return StoryGenerationResponse(
            story_id=story_id,
            status="completed",
            presentation_url=record["presentation_url"],
            video_url=record["video_url"],
            thumbnail_url=record["thumbnail_url"],
            narration_audio_url=narration_url,
            duration_seconds=duration_seconds,
            created_at=created_at,
            scenes=scenes,
        )
    except Exception as exc:
        logger.error("[Sard][%s] Generation pipeline failed: %s", story_id, exc, exc_info=True)
        user_message = _arabic_failure(exc)
        try:
            story_repository.save_story_record(
                {
                    "story_id": story_id,
                    "status": "failed",
                    "errors": [user_message],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as repository_exc:
            logger.warning(
                "[Sard][%s] Could not persist failed state: %s",
                story_id,
                repository_exc,
            )
        raise HTTPException(status_code=500, detail=user_message) from exc
