import asyncio
import logging
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.story import StoryGenerationRequest, StoryGenerationResponse
from app.services.job_repository import JobRepository, JobStoreUnavailable


logger = logging.getLogger(__name__)

GENERIC_FAILURE = "تعذر إكمال إنشاء القصة. يرجى إعادة المحاولة."

Runner = Callable[[StoryGenerationRequest], Awaitable[StoryGenerationResponse]]


class JobWorker:
    """Claims queued Jobs one at a time and runs the generation pipeline.

    One Job runs at a time: the MVP uses a single NotebookLM account, which
    runs one generation at a time.
    """

    def __init__(
        self,
        repository: JobRepository,
        runner: Runner,
        poll_interval: Optional[float] = None,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.poll_interval = settings.JOB_POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    async def process_one(self) -> bool:
        """Claim and run one Job. Returns False when nothing was waiting."""
        job = await asyncio.to_thread(self.repository.claim_next)
        if job is None:
            return False

        job_id = job["_id"]
        logger.info("[Sard][job %s] Claimed for story %s", job_id, job.get("story_id"))
        try:
            response = await self.runner(StoryGenerationRequest(**job["request"]))
            await asyncio.to_thread(self.repository.complete, job_id, response.model_dump())
            logger.info("[Sard][job %s] Completed", job_id)
        except HTTPException as exc:
            await asyncio.to_thread(self.repository.fail, job_id, str(exc.detail))
            logger.error("[Sard][job %s] Failed: %s", job_id, exc.detail)
        except JobStoreUnavailable:
            raise
        except Exception as exc:
            await asyncio.to_thread(self.repository.fail, job_id, GENERIC_FAILURE)
            logger.error("[Sard][job %s] Failed unexpectedly: %s", job_id, exc, exc_info=True)
        return True

    async def run_forever(self) -> None:
        while not self._stopping:
            try:
                if not await self.process_one():
                    await asyncio.sleep(self.poll_interval)
            except JobStoreUnavailable:
                logger.warning("[Sard] Job store unavailable; the worker will retry")
                await asyncio.sleep(max(self.poll_interval, 5))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Sard] Job worker error")
                await asyncio.sleep(self.poll_interval)
