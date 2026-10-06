import asyncio
import contextlib
import logging
import time
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from app.automation.errors import NeedsLoginError, QuotaExhaustedError
from app.core.config import settings
from app.schemas.story import StoryGenerationRequest
from app.services import pipeline
from app.services.job_repository import (
    NEEDS_LOGIN,
    QUOTA_EXHAUSTED,
    JobRepository,
    JobStoreUnavailable,
    LeaseLost,
)
from app.services.notebooklm_service import NotebookLMService, session_file_modified_at
from app.services.notifier import notify
from app.services.session_health import session_health
from app.services.pipeline import InsufficientSlidesError, PipelineContext, StageSpec
from app.services import temp_cleanup


logger = logging.getLogger(__name__)


def retry_delay_seconds(attempts: int) -> int:
    """Wait before the next try: 30 s after the first failure, then 2 min, then 10 min (configurable)."""
    backoff = settings.JOB_RETRY_BACKOFF_SECONDS or (30,)
    return backoff[min(max(attempts, 1) - 1, len(backoff) - 1)]


def quota_resume_at(now: datetime) -> datetime:
    """When to try again after NotebookLM refused new decks.

    At the configured daily reset time (UTC "HH:MM") if known; otherwise after a probe interval.
    """
    reset = settings.NOTEBOOKLM_QUOTA_RESET_UTC.strip()
    if reset:
        hour, minute = (int(part) for part in reset.split(":"))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    return now + timedelta(minutes=settings.NOTEBOOKLM_QUOTA_PROBE_MINUTES)


class Heartbeat:
    """Refreshes a Job's lease from its own thread while the Job runs.

    A thread, not an asyncio task: a Stage can block the event loop (ffmpeg runs
    synchronously), and a heartbeat that stops with it would let a healthy
    worker lose its Job. If the process dies the thread dies with it and the
    lease runs out, which is how another worker knows to take over.
    """

    def __init__(self, repository: JobRepository, job_id: str, worker_id: str, lease_seconds: float, interval: float):
        self.repository = repository
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval = interval
        self.lost = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{job_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                if not self.repository.heartbeat(self.job_id, self.worker_id, self.lease_seconds):
                    self.lost = True
                    logger.error("[Sard][job %s] Lease lost: another worker has taken this Job", self.job_id)
                    return
            except JobStoreUnavailable:
                logger.warning("[Sard][job %s] Heartbeat could not reach the job store; will try again", self.job_id)
            except Exception:
                logger.exception("[Sard][job %s] Heartbeat error", self.job_id)


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
        worker_id: Optional[str] = None,
        lease_seconds: Optional[float] = None,
        heartbeat_seconds: Optional[float] = None,
        browser_limiter: Optional[asyncio.Semaphore] = None,
        session_checker: Callable[[], Optional[datetime]] = session_file_modified_at,
        session_probe: Optional[Callable[[], Awaitable[bool]]] = None,
        notifier: Callable[[str, str], list] = notify,
    ) -> None:
        self.repository = repository
        # A quick visit to NotebookLM with the saved login: True if Google still treats it as signed in.
        self.session_probe = session_probe or (lambda: NotebookLMService().check_session())
        self.notifier = notifier
        # When the saved NotebookLM login was last written; a newer file means someone logged in again.
        self.session_checker = session_checker
        # Shared by every worker in this process: caps how many NotebookLM browsers are open at once.
        self.browser_limiter = browser_limiter
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.lease_seconds = settings.JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds
        heartbeat = settings.JOB_HEARTBEAT_SECONDS if heartbeat_seconds is None else heartbeat_seconds
        # A heartbeat close to the lease would let a single slow beat lose the Job.
        self.heartbeat_seconds = min(heartbeat, self.lease_seconds / 3)
        self.stages = list(stages if stages is not None else pipeline.STAGES)
        self.poll_interval = settings.JOB_POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
        self._stopping = False
        self._last_purge = 0.0

    def stop(self) -> None:
        self._stopping = True

    def _context(self, job: dict) -> PipelineContext:
        request = StoryGenerationRequest(**job["request"])
        return PipelineContext(
            request=request,
            work_dir=pipeline.work_dir_for(request.story_id or job["_id"]),
            expansions=job.get("expansions", 0),
            partial={name: data.get("partial", {}) for name, data in (job.get("stages") or {}).items()},
            # Runs in the thread of a browser Stage, so it uses the plain synchronous repository.
            save_partial=lambda stage, data: self.repository.save_stage_partial(
                job["_id"], stage, data, worker_id=self.worker_id
            ),
        )

    async def process_one(self) -> bool:
        """Claim a Job and run it as far as it goes. Returns False when nothing was waiting."""
        job = await asyncio.to_thread(self.repository.claim_next, self.worker_id, self.lease_seconds)
        if job is None:
            return False

        job_id = job["_id"]
        if job.pop("_recovered", False):
            logger.warning(
                "[Sard][job %s] Taken over from a worker that stopped (takeover %s)", job_id, job.get("takeovers", 1)
            )
        logger.info("[Sard][job %s] Claimed by %s for story %s", job_id, self.worker_id, job.get("story_id"))

        heartbeat = Heartbeat(
            self.repository, job_id, self.worker_id, self.lease_seconds, self.heartbeat_seconds
        )
        heartbeat.start()
        try:
            await self._run_stages(job, heartbeat)
        except LeaseLost as exc:
            logger.error("[Sard][job %s] %s; abandoning it", job_id, exc)
        except asyncio.CancelledError:
            # Shutting down: give the Job back now instead of making others wait out the lease.
            try:
                self.repository.release(job_id, self.worker_id)
            except Exception:
                logger.warning("[Sard][job %s] Could not release the Job on shutdown", job_id)
            raise
        finally:
            heartbeat.stop()
        return True

    async def _run_stages(self, job: dict, heartbeat: Heartbeat) -> None:
        job_id = job["_id"]
        ctx = self._context(job)
        saved_stages = job.get("stages") or {}
        write = {"worker_id": self.worker_id}

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

            # Only so many NotebookLM browsers may be open at once; a Job waits its turn here.
            limiter = self.browser_limiter if (spec.uses_browser and self.browser_limiter) else contextlib.nullcontext()
            async with limiter:
                if spec.uses_browser and await self._service_is_blocked(job_id, spec.name):
                    return
                attempts = await asyncio.to_thread(
                    self.repository.start_stage, job_id, spec.name, spec.progress, spec.step, **write
                )
                if attempts > settings.JOB_STAGE_MAX_ATTEMPTS:
                    # Every attempt was used, the last ones by workers that died mid-Stage:
                    # this Job keeps killing its workers, so stop feeding it new ones.
                    logger.error("[Sard][job %s] Stage %s keeps stopping its worker; moving to dead letter", job_id, spec.name)
                    await asyncio.to_thread(
                        self.repository.dead_letter,
                        job_id,
                        pipeline.arabic_failure(RuntimeError()),
                        spec.name,
                        f"Worker stopped during stage {spec.name} {attempts - 1} times",
                        None,
                        **write,
                    )
                    return
                logger.info("[Sard][job %s] Stage %s starting (attempt %s)", job_id, spec.name, attempts)
                try:
                    output = await spec.run(ctx)
                except (JobStoreUnavailable, LeaseLost):
                    raise
                except Exception as exc:
                    await self._handle_failure(job, spec, attempts, exc)
                    return
            if heartbeat.lost:
                raise LeaseLost(f"Job {job_id} was taken over while stage {spec.name} ran")
            ctx.outputs[spec.name] = output
            await asyncio.to_thread(self.repository.save_stage_output, job_id, spec.name, output, **write)

        result = ctx.outputs[self.stages[-1].name]
        await asyncio.to_thread(self.repository.complete, job_id, result, **write)
        logger.info("[Sard][job %s] Completed", job_id)
        # The Job is done: keep only the files its result links to. Never let this fail the Job.
        try:
            await asyncio.to_thread(temp_cleanup.trim_after_completion, ctx.story_id, result)
        except Exception as exc:
            logger.warning("[Sard][job %s] Temporary files could not be cleaned up: %s", job_id, exc)

    async def _handle_failure(self, job: dict, spec: StageSpec, attempts: int, exc: Exception) -> None:
        job_id = job["_id"]
        error = pipeline.arabic_failure(exc)
        detail = f"{type(exc).__name__}: {exc}"
        evidence_dir = getattr(exc, "evidence_dir", None)
        write = {"worker_id": self.worker_id}

        if isinstance(exc, (NeedsLoginError, QuotaExhaustedError)):
            await self._park(job_id, spec.name, exc)
            return

        if isinstance(exc, InsufficientSlidesError):
            if job.get("expansions", 0) < settings.GENERATION_RETRY_LIMIT:
                logger.warning("[Sard][job %s] Deck too short (%s slides); asking for a longer one", job_id, exc.count)
                await asyncio.to_thread(
                    self.repository.reset_stages, job_id, [s.name for s in self.stages], True, **write
                )
            else:
                logger.error("[Sard][job %s] Deck still too short after the controlled retry", job_id)
                await asyncio.to_thread(self.repository.fail, job_id, error, spec.name, detail, evidence_dir, **write)
            return

        if not pipeline.is_transient(exc):
            logger.error("[Sard][job %s] Stage %s failed and cannot be retried: %s", job_id, spec.name, detail)
            await asyncio.to_thread(self.repository.fail, job_id, error, spec.name, detail, evidence_dir, **write)
        elif attempts < settings.JOB_STAGE_MAX_ATTEMPTS:
            delay = retry_delay_seconds(attempts)
            run_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
            logger.warning(
                "[Sard][job %s] Stage %s failed (attempt %s/%s): %s; retrying in %ss",
                job_id, spec.name, attempts, settings.JOB_STAGE_MAX_ATTEMPTS, detail, delay,
            )
            await asyncio.to_thread(
                self.repository.schedule_retry, job_id, spec.name, error, run_after, detail, evidence_dir, **write
            )
        else:
            logger.error(
                "[Sard][job %s] Stage %s used all %s attempts; moving to dead letter: %s",
                job_id, spec.name, attempts, detail,
            )
            await asyncio.to_thread(self.repository.dead_letter, job_id, error, spec.name, detail, evidence_dir, **write)

    async def _tell_a_person(self, title: str, message: str) -> None:
        """Notify, without ever letting a failing notification disturb the worker."""
        try:
            await asyncio.to_thread(self.notifier, title, message)
        except Exception as exc:
            logger.warning("[Sard] Could not send the notification: %s", exc)

    async def _announce_block(self, kind: str, waiting: int, resume_at: Optional[datetime], first: bool) -> None:
        """Tell a person NotebookLM cannot be used. Only the first Job to find out says so, not every one."""
        if not first:
            return
        if kind == NEEDS_LOGIN:
            await self._tell_a_person(
                "NotebookLM login needed",
                f"The saved NotebookLM login has expired. {waiting} job(s) are waiting, not failed. "
                "Run `npm run auth` to sign in again; they resume by themselves.",
            )
        else:
            when = resume_at.strftime("%Y-%m-%d %H:%M UTC") if resume_at else "an unknown time"
            await self._tell_a_person(
                "NotebookLM quota reached",
                f"NotebookLM refused new decks. {waiting} job(s) are waiting, not failed, and will be tried again at {when}.",
            )

    async def _park(self, job_id: str, stage: str, exc: Exception) -> None:
        """NotebookLM cannot be used right now: wait instead of failing, and tell everyone waiting."""
        if isinstance(exc, NeedsLoginError):
            kind, resume_at = NEEDS_LOGIN, None
        else:
            kind, resume_at = QUOTA_EXHAUSTED, quota_resume_at(datetime.now(timezone.utc))
        flag_before = await asyncio.to_thread(self.repository.get_service_flag)
        first = flag_before is None or flag_before.get("status") != kind
        parked_others = await asyncio.to_thread(self.repository.block_service, kind, str(exc), resume_at)
        await asyncio.to_thread(
            self.repository.park_job, job_id, kind, stage, True, self.worker_id
        )
        await self._announce_block(kind, parked_others + 1, resume_at, first)
        if kind == NEEDS_LOGIN:
            logger.error(
                "[Sard] NotebookLM LOGIN EXPIRED: job %s and %s other waiting job(s) are parked, not failed. "
                "Run `npm run auth` to log in again; they resume by themselves.",
                job_id,
                parked_others,
            )
        else:
            logger.error(
                "[Sard] NotebookLM QUOTA REACHED: job %s and %s other waiting job(s) are parked, not failed. "
                "They resume at %s.",
                job_id,
                parked_others,
                resume_at.isoformat() if resume_at else "an unknown time",
            )

    async def _service_is_blocked(self, job_id: str, stage: str) -> bool:
        """If NotebookLM is known to be unusable, park this Job without opening a browser to find out again."""
        flag = await asyncio.to_thread(self.repository.get_service_flag)
        if not flag or flag.get("status") not in (NEEDS_LOGIN, QUOTA_EXHAUSTED):
            return False
        logger.info("[Sard][job %s] NotebookLM is %s; parking instead of opening a browser", job_id, flag["status"])
        await asyncio.to_thread(self.repository.park_job, job_id, flag["status"], stage, False, self.worker_id)
        return True

    async def purge_if_due(self) -> list[str]:
        """Clear old working files, at most once per JOB_TEMP_PURGE_INTERVAL_SECONDS."""
        if time.monotonic() - self._last_purge < settings.JOB_TEMP_PURGE_INTERVAL_SECONDS and self._last_purge:
            return []
        self._last_purge = time.monotonic()
        try:
            return await asyncio.to_thread(temp_cleanup.purge_stale, self.repository)
        except JobStoreUnavailable:
            raise
        except Exception as exc:
            logger.warning("[Sard] Purging old working files failed: %s", exc)
            return []

    async def resume_if_ready(self) -> int:
        """Unpark Jobs once the login has been renewed or the quota is due to reset. Returns how many resumed."""
        flag = await asyncio.to_thread(self.repository.get_service_flag)
        if not flag:
            return 0
        since = flag["since"].replace(tzinfo=timezone.utc) if flag["since"].tzinfo is None else flag["since"]

        if flag["status"] == NEEDS_LOGIN:
            saved = self.session_checker()
            if saved is None or saved <= since:
                return 0
            reason = "the login was renewed"
        elif flag["status"] == QUOTA_EXHAUSTED:
            resume_at = flag.get("resume_at")
            if resume_at is None:
                return 0
            if resume_at.tzinfo is None:
                resume_at = resume_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < resume_at:
                return 0
            reason = "the quota is due to reset"
        else:
            return 0

        resumed = await asyncio.to_thread(self.repository.unblock_service, flag["status"])
        logger.warning("[Sard] NotebookLM usable again (%s): resumed %s parked job(s)", reason, resumed)
        await self._tell_a_person("NotebookLM is usable again", f"Resumed {resumed} waiting job(s).")
        return resumed

    async def session_check_if_due(self) -> Optional[str]:
        """Now and then, check that the saved login is still good, and warn before it is not.

        Reads the cookies' expiry (no browser), and visits NotebookLM with the login (which also refreshes
        the saved cookies). Finding the login dead flags NotebookLM as needing a login, so waiting jobs
        are parked and a person is told before more users submit. Returns what it found, or None if not due.
        """
        hours = settings.NOTEBOOKLM_SESSION_CHECK_HOURS
        if hours <= 0:
            return None
        now = datetime.now(timezone.utc)
        state = await asyncio.to_thread(self.repository.get_session_state)
        last = state.get("last_checked_at")
        if last is not None:
            last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
            if now - last < timedelta(hours=hours):
                return None
        # Take the slot first, so several workers do not all check at once.
        await asyncio.to_thread(self.repository.update_session_state, last_checked_at=now)

        flag = await asyncio.to_thread(self.repository.get_service_flag)
        if flag and flag.get("status") == NEEDS_LOGIN:
            return "already_flagged"  # a person has already been told

        health = session_health()
        if health["state"] in ("missing", "invalid", "expired"):
            await self._flag_login_needed(f"The saved NotebookLM login is {health['state']}.")
            return health["state"]

        if health["state"] == "expiring":
            await self._warn_once_a_day(
                state,
                now,
                "NotebookLM login expires soon",
                f"The saved NotebookLM login expires in about {health['days_left']} day(s). "
                "Run `npm run auth` to sign in again before it does.",
            )

        # A visit with the login. It shares the browser limit with jobs, so it waits its turn.
        async with (self.browser_limiter or contextlib.nullcontext()):
            still_good = await self.session_probe()
        if still_good:
            await asyncio.to_thread(self.repository.update_session_state, last_ok_at=datetime.now(timezone.utc))
            return "ok"
        await self._flag_login_needed("NotebookLM redirected to Google's sign-in page.")
        return "signed_out"

    async def _flag_login_needed(self, reason: str) -> None:
        flag_before = await asyncio.to_thread(self.repository.get_service_flag)
        first = flag_before is None or flag_before.get("status") != NEEDS_LOGIN
        waiting = await asyncio.to_thread(self.repository.block_service, NEEDS_LOGIN, reason, None)
        logger.error("[Sard] NotebookLM LOGIN NEEDED (%s): %s waiting job(s) parked. Run `npm run auth`.", reason, waiting)
        await self._announce_block(NEEDS_LOGIN, waiting, None, first)

    async def _warn_once_a_day(self, state: dict, now: datetime, title: str, message: str) -> None:
        last = state.get("last_expiry_alert_at")
        if last is not None:
            last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
            if now - last < timedelta(hours=24):
                return
        await asyncio.to_thread(self.repository.update_session_state, last_expiry_alert_at=now)
        await self._tell_a_person(title, message)

    async def run_forever(self) -> None:
        while not self._stopping:
            try:
                await self.resume_if_ready()
                await self.session_check_if_due()
                await self.purge_if_due()
                if not await self.process_one():
                    await asyncio.sleep(self.poll_interval)
            except LeaseLost:
                logger.error("[Sard] Lost a Job's lease while updating it")
            except JobStoreUnavailable:
                logger.warning("[Sard] Job store unavailable; the worker will retry")
                await asyncio.sleep(max(self.poll_interval, 5))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Sard] Job worker error")
                await asyncio.sleep(self.poll_interval)
