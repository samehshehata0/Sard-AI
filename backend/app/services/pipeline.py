"""The story generation pipeline, split into Stages.

Each Stage takes the request plus the outputs of the Stages before it and
returns a small JSON-friendly output (paths, URLs, durations). Because outputs
are persisted on the Job, a failed Stage is retried on its own and the Stages
before it are never repeated: a narration failure no longer costs another
20-minute NotebookLM run.

The stages are:
    notebooklm      NotebookLM builds the slide deck (Submit and Collect are
                    split into two Stages in a later step)
    extract_slides  deck -> one image and one text per slide
    narrate         one narration audio file per slide
    compose         combined audio, and video unless audio-only
    upload          assets are uploaded and the final scenes are built
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.automation.errors import NotebookLMGenerationError, PermanentStepError, TransientStepError
from app.core.config import settings
from app.schemas.story import GeneratedScene, StoryGenerationRequest, StoryGenerationResponse
from app.services.imagekit_uploader import ImageKitUploader
from app.services.media_validation import MediaValidationError
from app.services.narration_builder import NarrationBuilder
from app.services.narration_service import NarrationGenerationError, NarrationService
from app.services.notebooklm_service import NotebookLMService
from app.services.prompt_builder import PromptBuilder
from app.services.slide_extractor import SlideExtractor
from app.services.story_repository import StoryRepository
from app.services.video_composer import VideoComposer, VideoCompositionError
from app.services.video_slide import VideoSlide


logger = logging.getLogger(__name__)

# Exact strings sent by the frontend wizard's "نوع المخرجات" dropdown
# (see wizard-form.tsx), forwarded unchanged through route.ts as output_type.
OUTPUT_TEXT_ONLY = "نص فقط"
OUTPUT_TEXT_AUDIO = "نص + صوت"
OUTPUT_TEXT_AUDIO_VIDEO = "نص + صوت + فيديو"

prompt_builder = PromptBuilder()
slide_extractor = SlideExtractor()
narration_builder = NarrationBuilder()
narration_service = NarrationService()
video_composer = VideoComposer()
imagekit_uploader = ImageKitUploader()
story_repository = StoryRepository()


class InsufficientSlidesError(TransientStepError):
    """NotebookLM returned too few slides; the whole deck should be asked for again, longer."""

    def __init__(self, count: int):
        super().__init__(f"NotebookLM returned {count} unique slides, fewer than the {settings.MIN_SLIDES} required")
        self.count = count


@dataclass
class PipelineContext:
    request: StoryGenerationRequest
    work_dir: str
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # How many times the deck was asked for again because it came back too short.
    expansions: int = 0

    @property
    def expansion_retry(self) -> bool:
        return self.expansions > 0

    @property
    def attempt_number(self) -> int:
        return self.expansions + 1

    @property
    def story_id(self) -> str:
        return self.request.story_id or ""


@dataclass(frozen=True)
class StageSpec:
    name: str
    run: Callable[[PipelineContext], Awaitable[dict[str, Any]]]
    progress: int
    step: str
    # Can a stored output still be used (are the files it points at still there)?
    is_valid: Callable[[PipelineContext, dict[str, Any]], bool] = lambda ctx, output: True


def arabic_failure(exc: Exception) -> str:
    if isinstance(exc, NotebookLMGenerationError):
        return exc.user_message
    if isinstance(exc, NarrationGenerationError):
        return exc.user_message
    if isinstance(exc, (VideoCompositionError, MediaValidationError)):
        return "تعذر إنشاء فيديو صالح بالصوت والصورة. يرجى إعادة المحاولة."
    if isinstance(exc, TimeoutError):
        return "انتهت مهلة إنشاء القصة. يرجى إعادة المحاولة."
    return "تعذر إكمال إنشاء القصة. يرجى إعادة المحاولة."


def is_transient(exc: Exception) -> bool:
    """Can trying again plausibly help? Unknown failures get the benefit of the doubt, within the attempt limit."""
    if isinstance(exc, NotebookLMGenerationError):
        return exc.retryable is not False
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return False
    return True


def _files_exist(paths: list[str]) -> bool:
    return all(os.path.isfile(path) for path in paths)


def _texts_for_unique_slides(all_texts: list[str], slide_images: list[str]) -> list[str]:
    result: list[str] = []
    for image_path in slide_images:
        try:
            page_number = int(Path(image_path).stem.rsplit("_", 1)[1])
            result.append(all_texts[page_number - 1] if page_number <= len(all_texts) else "")
        except (IndexError, ValueError):
            result.append("")
    return result


def _output_type(ctx: PipelineContext) -> str:
    return (ctx.request.output_type or "").strip()


def rebuild_slides(ctx: PipelineContext) -> list[VideoSlide]:
    """The slides, rebuilt from persisted outputs. The builder is deterministic."""
    extracted = ctx.outputs["extract_slides"]
    slides = narration_builder.build(ctx.request, extracted["slide_images"], extracted["slide_texts"])
    audio_by_index = {item["index"]: item for item in ctx.outputs.get("narrate", {}).get("audio", [])}
    durations = ctx.outputs.get("compose", {}).get("display_durations", [])
    for position, slide in enumerate(slides):
        audio = audio_by_index.get(slide.index)
        if audio:
            slide.audio_path = audio["path"]
            slide.audio_duration = audio["duration"]
        if position < len(durations):
            slide.display_duration = durations[position]
    return slides


# --- stages ----------------------------------------------------------------


async def run_notebooklm(ctx: PipelineContext) -> dict[str, Any]:
    os.makedirs(ctx.work_dir, exist_ok=True)
    story_md_path = os.path.join(ctx.work_dir, "story.md")
    Path(story_md_path).write_text(prompt_builder.build_story_markdown(ctx.request), encoding="utf-8")

    # Retries inside one attempt share a folder, so a half-finished notebook is resumed, not recreated.
    attempt_dir = os.path.join(ctx.work_dir, f"notebooklm_attempt_{ctx.attempt_number}")
    prompt = prompt_builder.build_notebooklm_prompt(ctx.request, expansion_retry=ctx.expansion_retry)
    presentation_path = await NotebookLMService().run_pipeline(story_md_path, prompt, attempt_dir)
    return {"presentation_path": presentation_path}


async def run_extract_slides(ctx: PipelineContext) -> dict[str, Any]:
    presentation_path = ctx.outputs["notebooklm"]["presentation_path"]
    slides_dir = os.path.join(ctx.work_dir, f"slides_attempt_{ctx.attempt_number}")
    slide_images = await slide_extractor.extract_slides(presentation_path, slides_dir)
    all_texts = slide_extractor.extract_slide_texts(presentation_path)
    slide_texts = _texts_for_unique_slides(all_texts, slide_images)
    logger.info(
        "[Sard][%s] NotebookLM generated %s unique slides (attempt %s)",
        ctx.story_id,
        len(slide_images),
        ctx.attempt_number,
    )
    if len(slide_images) < settings.MIN_SLIDES:
        raise InsufficientSlidesError(len(slide_images))
    return {"slide_images": slide_images, "slide_texts": slide_texts}


async def run_narrate(ctx: PipelineContext) -> dict[str, Any]:
    if _output_type(ctx) == OUTPUT_TEXT_ONLY:
        logger.info("[Sard][%s] Output mode: نص فقط — skipping narration", ctx.story_id)
        return {"audio": []}

    req = ctx.request
    slides = narration_builder.build(req, ctx.outputs["extract_slides"]["slide_images"], ctx.outputs["extract_slides"]["slide_texts"])
    audio_dir = os.path.join(ctx.work_dir, "narration_segments")
    os.makedirs(audio_dir, exist_ok=True)

    audio = []
    for slide in slides:
        path = os.path.join(audio_dir, f"scene_{slide.index:02d}.mp3")
        info = None
        if os.path.isfile(path):
            try:  # a slide narrated before a failure is not narrated again
                info = narration_service.validate(path)
            except Exception:
                info = None
        if info is None:
            await narration_service.generate_narration(
                text=slide.narration_text,
                voice_gender=req.narrator_gender,
                voice_tone=req.voice_tone,
                output_path=path,
            )
            info = narration_service.validate(path)
        logger.info("[Sard][%s] Narration ready for slide %s: %.2fs", ctx.story_id, slide.index, info.duration)
        audio.append({"index": slide.index, "path": path, "duration": info.duration})
    return {"audio": audio}


async def run_compose(ctx: PipelineContext) -> dict[str, Any]:
    slides = rebuild_slides(ctx)
    output_type = _output_type(ctx)

    if output_type == OUTPUT_TEXT_ONLY:
        # No audio or video here, but every scene still needs a duration.
        for slide in slides:
            slide.display_duration = settings.MIN_SLIDE_DURATION
        return {
            "video_path": "",
            "thumbnail_path": "",
            "narration_path": "",
            "duration_seconds": sum(slide.display_duration for slide in slides),
            "display_durations": [slide.display_duration for slide in slides],
        }

    narration_path = os.path.join(ctx.work_dir, "narration.mp3")
    video_path = ""
    if output_type == OUTPUT_TEXT_AUDIO:
        narration_path, thumbnail_path, duration = await video_composer.compose_audio_only(
            slides=slides,
            output_dir=os.path.join(ctx.work_dir, "audio"),
            narration_output_path=narration_path,
        )
    else:
        if output_type != OUTPUT_TEXT_AUDIO_VIDEO:
            logger.warning(
                "[Sard][%s] Unrecognized output_type '%s'; defaulting to the full نص + صوت + فيديو pipeline",
                ctx.story_id,
                ctx.request.output_type,
            )
        video_path, thumbnail_path, duration = await video_composer.compose_video(
            slides=slides,
            output_dir=os.path.join(ctx.work_dir, "video"),
            narration_output_path=narration_path,
        )
    return {
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
        "narration_path": narration_path,
        "duration_seconds": duration,
        "display_durations": [slide.display_duration for slide in slides],
    }


async def run_upload(ctx: PipelineContext) -> dict[str, Any]:
    req = ctx.request
    story_id = ctx.story_id
    slides = rebuild_slides(ctx)
    composed = ctx.outputs["compose"]

    uploaded_urls = await imagekit_uploader.upload_assets(
        presentation_path=ctx.outputs["notebooklm"]["presentation_path"],
        video_path=composed["video_path"],
        thumbnail_path=composed["thumbnail_path"],
        story_id=story_id,
        narration_path=composed["narration_path"],
    )
    created_at = datetime.now(timezone.utc).isoformat()
    narration_url = uploaded_urls.get("narration_audio_url") or (
        f"http://127.0.0.1:8000/temp/{story_id}/narration.mp3" if composed["narration_path"] else None
    )
    scenes = [
        GeneratedScene(
            scene_number=slide.index,
            title=slide.title,
            visual_description=f"مادة بصرية تعليمية مولدة عبر NotebookLM حول {req.story_title}",
            narration_text=slide.narration_text,
            image_url=f"http://127.0.0.1:8000/temp/{story_id}/{os.path.relpath(slide.visual_path, ctx.work_dir).replace(os.sep, '/')}",
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
        "duration_seconds": composed["duration_seconds"],
        "scenes": [scene.model_dump() for scene in scenes],
        "created_at": created_at,
        "status": "completed",
    }
    story_repository.save_story_record(record)
    logger.info(
        "[Sard][%s] Generation completed: slides=%s duration=%.2fs",
        story_id,
        len(slides),
        composed["duration_seconds"],
    )
    return StoryGenerationResponse(
        story_id=story_id,
        status="completed",
        presentation_url=record["presentation_url"],
        video_url=record["video_url"],
        thumbnail_url=record["thumbnail_url"],
        narration_audio_url=narration_url,
        duration_seconds=composed["duration_seconds"],
        created_at=created_at,
        scenes=scenes,
    ).model_dump()


STAGES: list[StageSpec] = [
    StageSpec(
        "notebooklm",
        run_notebooklm,
        25,
        "جارٍ أتمتة Google NotebookLM وإنشاء العرض التقديمي والشرائح...",
        is_valid=lambda ctx, output: os.path.isfile(output.get("presentation_path", "")),
    ),
    StageSpec(
        "extract_slides",
        run_extract_slides,
        55,
        "جارٍ استخراج الشرائح من العرض التقديمي...",
        is_valid=lambda ctx, output: _files_exist(output.get("slide_images", [])),
    ),
    StageSpec(
        "narrate",
        run_narrate,
        65,
        "جارٍ إنشاء التعليق الصوتي...",
        is_valid=lambda ctx, output: _files_exist([item["path"] for item in output.get("audio", [])]),
    ),
    StageSpec(
        "compose",
        run_compose,
        80,
        "جارٍ تجميع الصوت والفيديو...",
        is_valid=lambda ctx, output: _files_exist(
            [path for path in (output.get("video_path"), output.get("thumbnail_path"), output.get("narration_path")) if path]
        ),
    ),
    StageSpec("upload", run_upload, 90, "جارٍ تجهيز الأصول النهائية ورفعها..."),
]


def work_dir_for(story_id: str) -> str:
    return os.path.join(settings.TEMP_DIR, story_id)


def new_context(req: StoryGenerationRequest) -> PipelineContext:
    story_id = req.story_id or str(uuid.uuid4())
    return PipelineContext(request=req.model_copy(update={"story_id": story_id}), work_dir=work_dir_for(story_id))


async def run_inline(req: StoryGenerationRequest) -> StoryGenerationResponse:
    """Run every Stage once, in this process, with no retry. The old synchronous endpoint uses this."""
    ctx = new_context(req)
    while True:
        try:
            for spec in STAGES:
                ctx.outputs[spec.name] = await spec.run(ctx)
            break
        except InsufficientSlidesError as exc:
            if ctx.expansions >= settings.GENERATION_RETRY_LIMIT:
                raise PermanentStepError(
                    f"NotebookLM returned {exc.count} unique slides after controlled retry"
                ) from exc
            ctx.expansions += 1
            ctx.outputs.clear()
    return StoryGenerationResponse(**ctx.outputs["upload"])
