import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.schemas.story import StoryGenerationRequest
from app.services import pipeline
from app.services.job_repository import JobRepository, JobStoreUnavailable
from app.services.pipeline import InsufficientSlidesError, PipelineContext, StageSpec


logger = logging.getLogger(__name__)


def retry_delay_seconds(attempts: int) -> int:
    """Wait before the next try: 30 s after the first failure, then 2 min, then 10 min (configurable)."""
    backoff = settings.JOB_RETRY_BACKOFF_SECONDS or (30,)
    return backoff[min(max(attempts, 1) - 1, len(backoff) - 1)]


class JobWorker:
    """Claims queued Jobs one at a time and runs their Stages.

    One Job runs at a time: the MVP uses a single NotebookLM account, which
    runs one generation at a time. A Stage that fails with a transient error
    puts the Job back in the queue to be retried later, so the worker is free
    for other Jobs meanwhile, and Stages that already finished are not repeated.
    """

    def __init__(
        self,
        repository: JobRepository,
        poll_interval: Optional[float] = None,
        stages: Optional[list[StageSpec]] = None,
    ) -> None:
        self.repository = repository
        self.stages = list(stages if stages is not None else pipeline.STAGES)
        self.poll_interval = settings.JOB_POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def _context(self, job: dict) -> PipelineContext:
        request = StoryGenerationRequest(**job["request"])
        return PipelineContext(
            request=request,
            work_dir=pipeline.work_dir_for(request.story_id or job["_id"]),
            expansions=job.get("expansions", 0),
        )

    async def process_one(self) -> bool:
        """Claim a Job and run it as far as it goes. Returns False when nothing was waiting."""
        job = await asyncio.to_thread(self.repository.claim_next)
        if job is None:
            return False

        job_id = job["_id"]
        logger.info("[Sard][job %s] Claimed for story %s", job_id, job.get("story_id"))
        ctx = self._context(job)
        saved_stages = job.get("stages") or {}

        reuse = True
        for spec in self.stages:
            saved = saved_stages.get(spec.name) or {}
            # A Stage whose output is still valid is skipped, but once one Stage has to run,
            # everything after it runs too: its inputs may have changed.
            if reuse and saved.get("state") == "done" and spec.is_valid(ctx, saved.get("output", {})):
                ctx.outputs[spec.name] = saved["output"]
                logger.info("[Sard][job %s] Stage %s already done; reusing its output", job_id, spec.name)
                continue
            reuse = False

            attempts = await asyncio.to_thread(
                self.repository.start_stage, job_id, spec.name, spec.progress, spec.step
            )
            logger.info("[Sard][job %s] Stage %s starting (attempt %s)", job_id, spec.name, attempts)
            try:
                output = await spec.run(ctx)
            except JobStoreUnavailable:
                raise
            except Exception as exc:
                await self._handle_failure(job, spec, attempts, exc)
                return True
            ctx.outputs[spec.name] = output
            await asyncio.to_thread(self.repository.save_stage_output, job_id, spec.name, output)

        await asyncio.to_thread(self.repository.complete, job_id, ctx.outputs[self.stages[-1].name])
        logger.info("[Sard][job %s] Completed", job_id)
        return True

    async def _handle_failure(self, job: dict, spec: StageSpec, attempts: int, exc: Exception) -> None:
        job_id = job["_id"]
        error = pipeline.arabic_failure(exc)
        detail = f"{type(exc).__name__}: {exc}"
        evidence_dir = getattr(exc, "evidence_dir", None)

        if isinstance(exc, InsufficientSlidesError):
            if job.get("expansions", 0) < settings.GENERATION_RETRY_LIMIT:
                logger.warning("[Sard][job %s] Deck too short (%s slides); asking for a longer one", job_id, exc.count)
                await asyncio.to_thread(self.repository.reset_stages, job_id, [s.name for s in self.stages], True)
            else:
                logger.error("[Sard][job %s] Deck still too short after the controlled retry", job_id)
                await asyncio.to_thread(self.repository.fail, job_id, error, spec.name, detail, evidence_dir)
            return

        if not pipeline.is_transient(exc):
            logger.error("[Sard][job %s] Stage %s failed and cannot be retried: %s", job_id, spec.name, detail)
            await asyncio.to_thread(self.repository.fail, job_id, error, spec.name, detail, evidence_dir)
        elif attempts < settings.JOB_STAGE_MAX_ATTEMPTS:
            delay = retry_delay_seconds(attempts)
            run_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
            logger.warning(
                "[Sard][job %s] Stage %s failed (attempt %s/%s): %s; retrying in %ss",
                job_id, spec.name, attempts, settings.JOB_STAGE_MAX_ATTEMPTS, detail, delay,
            )
            await asyncio.to_thread(
                self.repository.schedule_retry, job_id, spec.name, error, run_after, detail, evidence_dir
            )
        else:
            logger.error(
                "[Sard][job %s] Stage %s used all %s attempts; moving to dead letter: %s",
                job_id, spec.name, attempts, detail,
            )
            await asyncio.to_thread(self.repository.dead_letter, job_id, error, spec.name, detail, evidence_dir)

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
