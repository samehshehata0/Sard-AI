import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.story import StoryGenerationRequest, StoryGenerationResponse
from app.services import pipeline
# These shared instances are re-exported: the tests patch them through this module.
from app.services.pipeline import (  # noqa: F401
    imagekit_uploader,
    narration_builder,
    narration_service,
    prompt_builder,
    slide_extractor,
    story_repository,
    video_composer,
)


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate-story", response_model=StoryGenerationResponse)
async def generate_story(req: StoryGenerationRequest):
    """The old synchronous endpoint: runs every Stage once, in this request, with no retry."""
    story_id = req.story_id or pipeline.new_context(req).story_id
    logger.info("[Sard][%s] Generation started: title=%s", story_id, req.story_title)
    try:
        return await pipeline.run_inline(req.model_copy(update={"story_id": story_id}))
    except Exception as exc:
        logger.error("[Sard][%s] Generation pipeline failed: %s", story_id, exc, exc_info=True)
        user_message = pipeline.arabic_failure(exc)
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
