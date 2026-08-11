import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.schemas.story import StoryGenerationRequest, StoryGenerationResponse
from app.services.prompt_builder import PromptBuilder
from app.services.notebooklm_service import NotebookLMService
from app.services.presentation_downloader import PresentationDownloader
from app.services.presentation_parser import PresentationParser
from app.services.slide_generator import SlideGenerator
from app.services.slide_extractor import SlideExtractor
from app.services.narration_service import NarrationService
from app.services.video_composer import VideoComposer
from app.services.imagekit_uploader import ImageKitUploader
from app.services.story_repository import StoryRepository
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

prompt_builder = PromptBuilder()
downloader = PresentationDownloader()
parser = PresentationParser()
slide_generator = SlideGenerator()
slide_extractor = SlideExtractor()
narration_service = NarrationService()
video_composer = VideoComposer()
imagekit_uploader = ImageKitUploader()
story_repository = StoryRepository()

@router.post("/generate-story", response_model=StoryGenerationResponse)
async def generate_story(req: StoryGenerationRequest):
    """
    Complete story generation pipeline:
    1. Build story.md Markdown document.
    2. Render HD 16:9 RTL Arabic Presentation Deck HTML.
    3. Run Google NotebookLM Automation for research PDF.
    4. Extract HD 16:9 PNG slide images.
    5. Synthesize complete Arabic narration audio script.
    6. Compose full-length MP4 video presentation.
    7. Serve assets via static server / ImageKit.
    """
    story_id = req.story_id or str(uuid.uuid4())
    logger.info(f"[API] Received story generation request: '{req.story_title}' (ID: {story_id})")

    work_dir = os.path.join(settings.TEMP_DIR, story_id)
    os.makedirs(work_dir, exist_ok=True)

    try:
        # 1. Build Story Markdown & NotebookLM prompt
        story_md_content = prompt_builder.build_story_markdown(req)
        story_md_path = os.path.join(work_dir, "story.md")
        with open(story_md_path, "w", encoding="utf-8") as f:
            f.write(story_md_content)
            
        notebooklm_prompt = prompt_builder.build_notebooklm_prompt(req)

        # 2. Render HD 16:9 Presentation HTML Slides Deck
        html_presentation_path = os.path.join(work_dir, "presentation.html")
        slide_generator.generate_html_presentation(req, html_presentation_path)

        # 3. Run Google NotebookLM Automation
        notebooklm = NotebookLMService()
        presentation_file_path = html_presentation_path
        try:
            nb_res = await notebooklm.run_pipeline(story_md_path, notebooklm_prompt, work_dir)
            if nb_res and os.path.exists(nb_res):
                presentation_file_path = nb_res
        except Exception as e:
            logger.warning(f"[API] NotebookLM execution notice: {e}")

        # 4. Extract HD 16:9 Slide Images from Presentation Deck
        slides_dir = os.path.join(work_dir, "slides")
        slide_images = await slide_extractor.extract_slides(html_presentation_path, slides_dir)

        # 5. Generate Full Narration Script & Audio (20-30 seconds)
        objectives_text = " ".join(req.learning_objectives)
        narration_script_text = (
            f"مرحباً بكم في العرض التقديمي لقصة {req.story_title}. "
            f"{req.story_idea}. "
            f"نستعرض في هذا الدرس الأهداف التعليمية التالية: {objectives_text}. "
            f"المشهد الأول: انطلاقة الاكتشاف والموقف التعليمي الأساسي. "
            f"المشهد الثاني: تجربة الملاحظة وفهم العلاقات التطبيقية. "
            f"المشهد الثالث: التطبيق التربوي، والسلوك الإيجابي الملموس للوصول إلى النتيجة النهائية والنجاح."
        )
        audio_path = os.path.join(work_dir, "narration.mp3")
        await narration_service.generate_narration(
            text=narration_script_text,
            voice_gender=req.narrator_gender,
            output_path=audio_path
        )

        # 6. Compose Full Video Presentation & Thumbnail
        video_dir = os.path.join(work_dir, "video")
        video_path, thumbnail_path, duration_seconds = await video_composer.compose_video(
            slide_images=slide_images,
            audio_path=audio_path,
            narration_script=narration_script_text,
            output_dir=video_dir
        )

        # 7. Upload Assets to ImageKit / Static Server
        uploaded_urls = await imagekit_uploader.upload_assets(
            presentation_path=presentation_file_path,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            story_id=story_id
        )

        # 8. Persist Record to MongoDB (with graceful fallback)
        created_at_dt = datetime.utcnow()
        record = {
            "story_id": story_id,
            "user_id": "anonymous_user",
            "original_inputs": req.dict(),
            "notebooklm_prompt": notebooklm_prompt,
            "presentation_url": uploaded_urls.get("presentation_url"),
            "video_url": uploaded_urls.get("video_url"),
            "thumbnail_url": uploaded_urls.get("thumbnail_url"),
            "narration_audio_url": f"http://127.0.0.1:8000/temp/{story_id}/narration.mp3",
            "duration_seconds": duration_seconds,
            "scenes": [
                {
                    "scene_number": i + 1,
                    "title": f"المشهد {i + 1}",
                    "visual_description": f"عرض توضيحي للمشهد {i + 1}",
                    "narration_text": req.story_idea,
                    "image_url": f"http://127.0.0.1:8000/temp/{story_id}/slides/scene_{i + 1:02d}.png",
                    "duration_seconds": duration_seconds / max(1, len(slide_images))
                } for i in range(len(slide_images))
            ],
            "created_at": created_at_dt.isoformat()
        }

        try:
            story_repository.save_story_record(record)
        except Exception as repo_err:
            logger.warning(f"[API] Story repository save warning: {repo_err}")

        return StoryGenerationResponse(
            story_id=story_id,
            status="completed",
            presentation_url=record["presentation_url"],
            video_url=record["video_url"],
            thumbnail_url=record["thumbnail_url"],
            duration_seconds=duration_seconds,
            created_at=record["created_at"]
        )

    except Exception as e:
        logger.error(f"[API] Story generation pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Story generation failed: {str(e)}")
