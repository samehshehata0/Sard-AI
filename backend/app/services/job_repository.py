import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import settings


logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
# Failed with an error that retrying cannot fix.
FAILED = "failed"
# Gave up after using every attempt on a Stage; kept so an admin can requeue it.
DEAD_LETTER = "dead_letter"

WAITING_STEP = "بانتظار إعادة المحاولة..."

RUNNING_STEP = "جارٍ أتمتة Google NotebookLM وإنشاء العرض التقديمي والشرائح..."


class JobStoreUnavailable(RuntimeError):
    """MongoDB could not be reached. Jobs are never kept in memory instead."""


class LeaseLost(RuntimeError):
    """Another worker has taken this Job over. Whatever this worker was doing no longer counts."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guarded(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except PyMongoError as exc:
            logger.error("[JobRepository] MongoDB unavailable: %s", exc)
            raise JobStoreUnavailable(str(exc)) from exc

    return wrapper


class JobRepository:
    """Generation Jobs in a MongoDB collection.

    Unlike StoryRepository there is no in-memory fallback: a Job we cannot
    store durably must be refused, not accepted and lost on restart.
    """

    def __init__(self, collection) -> None:
        self.collection = collection

    @classmethod
    def connect(cls) -> "JobRepository":
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=settings.JOB_STORE_TIMEOUT_MS)
        return cls(client[settings.MONGODB_DB_NAME]["jobs"])

    @_guarded
    def ensure_indexes(self) -> None:
        self.collection.create_index([("state", ASCENDING), ("run_after", ASCENDING), ("created_at", ASCENDING)])
        self.collection.create_index([("story_id", ASCENDING)])

    @_guarded
    def enqueue(self, story_id: str, request: dict[str, Any], job_id: Optional[str] = None) -> dict[str, Any]:
        """Store a new queued Job. Enqueueing the same job_id again returns the existing Job."""
        now = _now()
        job = {
            "_id": job_id or str(uuid.uuid4()),
            "story_id": story_id,
            "request": request,
            "state": QUEUED,
            "progress": 0,
            "step": None,
            "attempts": 0,
            "run_after": now,
            "created_at": now,
            "updated_at": now,
        }
        try:
            self.collection.insert_one(job)
        except DuplicateKeyError:
            return self.collection.find_one({"_id": job["_id"]})
        return job

    @_guarded
    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        return self.collection.find_one({"_id": job_id})

    @_guarded
    def claim_next(self, worker_id: str = "", lease_seconds: Optional[float] = None) -> Optional[dict[str, Any]]:
        """Atomically take the oldest due queued Job, or else a running Job whose lease ran out.

        The Job is marked running and leased to `worker_id`. A Job taken over from a worker that
        died comes back with `_recovered` set (that key is not stored).
        """
        now = _now()
        lease = settings.JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds
        owner = {"state": RUNNING, "worker_id": worker_id, "lease_until": now + timedelta(seconds=lease), "updated_at": now}

        job = self.collection.find_one_and_update(
            {"state": QUEUED, "run_after": {"$lte": now}},
            {
                "$set": {**owner, "progress": 25, "step": RUNNING_STEP, "started_at": now},
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        if job is not None:
            return job

        job = self.collection.find_one_and_update(
            {"state": RUNNING, "lease_until": {"$lt": now}},
            {"$set": owner, "$inc": {"attempts": 1, "takeovers": 1}},
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        if job is not None:
            job["_recovered"] = True
        return job

    @_guarded
    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: Optional[float] = None) -> bool:
        """Extend the lease. False means the Job is no longer ours."""
        now = _now()
        lease = settings.JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds
        result = self.collection.update_one(
            {"_id": job_id, "state": RUNNING, "worker_id": worker_id},
            {"$set": {"lease_until": now + timedelta(seconds=lease), "updated_at": now}},
        )
        return result.matched_count == 1

    @_guarded
    def release(self, job_id: str, worker_id: str) -> bool:
        """Hand a Job back to the queue straight away, for example when this worker is shutting down."""
        now = _now()
        result = self.collection.update_one(
            {"_id": job_id, "state": RUNNING, "worker_id": worker_id},
            {"$set": {"state": QUEUED, "run_after": now, "step": WAITING_STEP, "updated_at": now}, "$unset": {"lease_until": ""}},
        )
        return result.matched_count == 1

    def _write(self, job_id: str, update: dict[str, Any], worker_id: Optional[str]) -> None:
        """Update a Job. With a worker_id the write only counts while that worker still holds the Job."""
        query: dict[str, Any] = {"_id": job_id}
        if worker_id is not None:
            query.update({"state": RUNNING, "worker_id": worker_id})
        result = self.collection.update_one(query, update)
        if worker_id is not None and result.matched_count == 0:
            raise LeaseLost(f"Job {job_id} is no longer held by worker {worker_id}")

    @_guarded
    def start_stage(
        self, job_id: str, stage: str, progress: int, step: str, worker_id: Optional[str] = None
    ) -> int:
        """Record that a Stage is starting. Returns how many attempts this Stage has now used."""
        now = _now()
        query: dict[str, Any] = {"_id": job_id}
        if worker_id is not None:
            query.update({"state": RUNNING, "worker_id": worker_id})
        job = self.collection.find_one_and_update(
            query,
            {
                "$inc": {f"stages.{stage}.attempts": 1},
                "$set": {
                    "stage": stage,
                    "progress": progress,
                    "step": step,
                    f"stages.{stage}.state": "running",
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if job is None:
            raise LeaseLost(f"Job {job_id} is no longer held by worker {worker_id}")
        return job["stages"][stage]["attempts"]

    @_guarded
    def save_stage_output(
        self, job_id: str, stage: str, output: dict[str, Any], worker_id: Optional[str] = None
    ) -> None:
        self._write(
            job_id,
            {"$set": {f"stages.{stage}.state": "done", f"stages.{stage}.output": output, "updated_at": _now()}},
            worker_id,
        )

    @staticmethod
    def _evidence(stage: str, error: str, detail: str, evidence_dir: Optional[str]) -> dict[str, Any]:
        return {"stage": stage, "at": _now(), "error": error, "detail": detail, "evidence_dir": evidence_dir}

    @_guarded
    def schedule_retry(
        self,
        job_id: str,
        stage: str,
        error: str,
        run_after: datetime,
        detail: str = "",
        evidence_dir: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """Put the Job back in the queue to be tried again later, keeping every finished Stage."""
        self._write(
            job_id,
            {
                "$set": {
                    "state": QUEUED,
                    "run_after": run_after,
                    "step": WAITING_STEP,
                    "error": error,
                    f"stages.{stage}.state": "waiting",
                    "updated_at": _now(),
                },
                "$unset": {"lease_until": ""},
                "$push": {"failures": self._evidence(stage, error, detail, evidence_dir)},
            },
            worker_id,
        )

    @_guarded
    def reset_stages(
        self, job_id: str, stages: list[str], expand: bool = False, worker_id: Optional[str] = None
    ) -> None:
        """Forget the output of some Stages and queue the Job to run again straight away."""
        now = _now()
        update: dict[str, Any] = {
            "$set": {"state": QUEUED, "run_after": now, "step": WAITING_STEP, "updated_at": now},
            "$unset": {**{f"stages.{stage}": "" for stage in stages}, "lease_until": ""},
        }
        if expand:
            update["$inc"] = {"expansions": 1}
        self._write(job_id, update, worker_id)

    @_guarded
    def complete(self, job_id: str, result: dict[str, Any], worker_id: Optional[str] = None) -> None:
        now = _now()
        self._write(
            job_id,
            {
                "$set": {"state": COMPLETED, "progress": 100, "result": result, "finished_at": now, "updated_at": now},
                "$unset": {"error": "", "lease_until": ""},
            },
            worker_id,
        )

    def _finish(
        self,
        state: str,
        job_id: str,
        error: str,
        stage: Optional[str],
        detail: str,
        evidence_dir: Optional[str],
        worker_id: Optional[str],
    ) -> None:
        now = _now()
        update: dict[str, Any] = {
            "$set": {"state": state, "error": error, "finished_at": now, "updated_at": now},
            "$unset": {"lease_until": ""},
        }
        if stage:
            update["$push"] = {"failures": self._evidence(stage, error, detail, evidence_dir)}
        self._write(job_id, update, worker_id)

    @_guarded
    def fail(
        self,
        job_id: str,
        error: str,
        stage: Optional[str] = None,
        detail: str = "",
        evidence_dir: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """The Job failed in a way that retrying cannot fix."""
        self._finish(FAILED, job_id, error, stage, detail, evidence_dir, worker_id)

    @_guarded
    def dead_letter(
        self,
        job_id: str,
        error: str,
        stage: str,
        detail: str = "",
        evidence_dir: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """The Job used every attempt on a Stage. It is kept, with its error and evidence."""
        self._finish(DEAD_LETTER, job_id, error, stage, detail, evidence_dir, worker_id)

    @_guarded
    def requeue(self, job_id: str) -> bool:
        """Queue a failed or dead-lettered Job again. Finished Stages are reused; the one that failed gets fresh attempts."""
        job = self.collection.find_one({"_id": job_id})
        if job is None or job["state"] not in (FAILED, DEAD_LETTER):
            return False
        now = _now()
        update: dict[str, Any] = {
            "$set": {"state": QUEUED, "run_after": now, "step": WAITING_STEP, "updated_at": now},
            "$unset": {"error": "", "finished_at": "", "lease_until": ""},
        }
        failed_stage = job.get("stage")
        if failed_stage:
            update["$set"][f"stages.{failed_stage}.attempts"] = 0
        self.collection.update_one({"_id": job_id}, update)
        return True


def public_view(job: dict[str, Any]) -> dict[str, Any]:
    """The Job as the API reports it: no stored request, ISO timestamps."""

    def iso(value):
        return value.isoformat() if isinstance(value, datetime) else value

    return {
        "job_id": job["_id"],
        "story_id": job.get("story_id"),
        "state": job["state"],
        "progress": job.get("progress", 0),
        "step": job.get("step"),
        "attempts": job.get("attempts", 0),
        "stage": job.get("stage"),
        "stages": {
            name: {"state": data.get("state"), "attempts": data.get("attempts", 0)}
            for name, data in (job.get("stages") or {}).items()
        },
        "run_after": iso(job.get("run_after")),
        "error": job.get("error"),
        "result": job.get("result"),
        "created_at": iso(job.get("created_at")),
        "started_at": iso(job.get("started_at")),
        "finished_at": iso(job.get("finished_at")),
    }
