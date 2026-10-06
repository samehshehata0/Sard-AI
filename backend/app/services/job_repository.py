import hashlib
import json
import logging
import re
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
# Cancelled by its user while still waiting in the queue.
CANCELLED = "cancelled"

# Parked: waiting for a person or for time to pass, not failed. They keep every finished Stage and
# the attempts they had; they resume by themselves once the cause is gone.
NEEDS_LOGIN = "needs_login"
QUOTA_EXHAUSTED = "quota_exhausted"
PARKED_STATES = [NEEDS_LOGIN, QUOTA_EXHAUSTED]

# A user's active Jobs: everything that is not finished yet, parked ones included.
ACTIVE_STATES = [QUEUED, RUNNING, *PARKED_STATES]

SERVICE_FLAG_ID = "notebooklm"
SESSION_STATE_ID = "notebooklm_session"
PARKED_STEPS = {
    NEEDS_LOGIN: "بانتظار تسجيل الدخول إلى NotebookLM. سيُستأنف التوليد تلقائيًا بعد تجديد الجلسة.",
    QUOTA_EXHAUSTED: "تم بلوغ الحد اليومي لإنشاء العروض في NotebookLM. سيُستأنف التوليد تلقائيًا عند تجدد الحصة.",
}
CANCELLED_MESSAGE = "أُلغي طلب التوليد."

WAITING_STEP = "بانتظار إعادة المحاولة..."

RUNNING_STEP = "جارٍ أتمتة Google NotebookLM وإنشاء العرض التقديمي والشرائح..."


class JobStoreUnavailable(RuntimeError):
    """MongoDB could not be reached. Jobs are never kept in memory instead."""


class UserJobLimitReached(RuntimeError):
    """The user already has as many queued or running Jobs as they are allowed."""

    def __init__(self, active: int, limit: int):
        super().__init__(f"{active} active Jobs, limit {limit}")
        self.active = active
        self.limit = limit


class LeaseLost(RuntimeError):
    """Another worker has taken this Job over. Whatever this worker was doing no longer counts."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip() or None
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def fingerprint(request: dict[str, Any]) -> str:
    """The same story request always gets the same fingerprint: ids are left out, text is tidied."""
    material = {key: value for key, value in request.items() if key not in {"story_id", "job_id", "user_id"}}
    encoded = json.dumps(_normalize(material), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
        self._indexes_ready = False

    @property
    def flags(self):
        """Service-wide state, such as "NotebookLM needs a login", next to the Jobs."""
        return self.collection.database["service_state"]

    @classmethod
    def connect(cls) -> "JobRepository":
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=settings.JOB_STORE_TIMEOUT_MS)
        return cls(client[settings.MONGODB_DB_NAME]["jobs"])

    @_guarded
    def ensure_indexes(self) -> None:
        self.collection.create_index([("state", ASCENDING), ("run_after", ASCENDING), ("created_at", ASCENDING)])
        self.collection.create_index([("story_id", ASCENDING)])
        self.collection.create_index([("user_id", ASCENDING), ("state", ASCENDING)])
        # Only a Job that is still active carries this key, so at most one active Job per user
        # can have a given fingerprint even when two submissions arrive at the same moment.
        self.collection.create_index([("active_fingerprint", ASCENDING)], unique=True, sparse=True)
        self._indexes_ready = True

    def _ensure_indexes_once(self) -> None:
        if not self._indexes_ready:
            self.ensure_indexes()

    @_guarded
    def submit(
        self,
        story_id: str,
        request: dict[str, Any],
        user_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> tuple[dict[str, Any], bool]:
        """Queue a Job for a user, with the fairness rules applied.

        Returns (job, duplicate). The same request that is still queued or running is not queued
        twice: the existing Job comes back with duplicate=True. A user over their limit of active
        Jobs gets UserJobLimitReached. Without a user_id there are no rules.
        """
        if not user_id:
            return self.enqueue(story_id, request, job_id=job_id), False

        self._ensure_indexes_once()
        key = f"{user_id}:{fingerprint(request)}"
        existing = self.collection.find_one({"active_fingerprint": key})
        if existing is not None:
            return existing, True

        active = self.collection.count_documents({"user_id": user_id, "state": {"$in": ACTIVE_STATES}})
        if active >= settings.JOB_MAX_ACTIVE_PER_USER:
            raise UserJobLimitReached(active, settings.JOB_MAX_ACTIVE_PER_USER)

        job = self._new_job(story_id, request, job_id)
        job.update({"user_id": user_id, "fingerprint": key.split(":", 1)[1], "active_fingerprint": key})
        try:
            self.collection.insert_one(job)
        except DuplicateKeyError:
            # Two identical submissions arrived together; the other one won.
            winner = self.collection.find_one({"active_fingerprint": key}) or self.collection.find_one({"_id": job["_id"]})
            return winner, True
        return job, False

    @_guarded
    def cancel(self, job_id: str, user_id: str) -> str:
        """Cancel a Job that is still waiting. Returns cancelled, not_found, forbidden or not_cancellable."""
        now = _now()
        cancelled = self.collection.find_one_and_update(
            {"_id": job_id, "state": {"$in": [QUEUED, *PARKED_STATES]}, "user_id": user_id},
            {
                "$set": {"state": CANCELLED, "error": CANCELLED_MESSAGE, "finished_at": now, "updated_at": now},
                "$unset": {"lease_until": "", "active_fingerprint": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        if cancelled is not None:
            return "cancelled"
        job = self.collection.find_one({"_id": job_id})
        if job is None:
            return "not_found"
        if job.get("user_id") != user_id:
            return "forbidden"
        return "not_cancellable"

    @staticmethod
    def _new_job(story_id: str, request: dict[str, Any], job_id: Optional[str]) -> dict[str, Any]:
        now = _now()
        return {
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

    @_guarded
    def enqueue(self, story_id: str, request: dict[str, Any], job_id: Optional[str] = None) -> dict[str, Any]:
        """Store a new queued Job, with no fairness rules. The same job_id again returns the existing Job."""
        job = self._new_job(story_id, request, job_id)
        try:
            self.collection.insert_one(job)
        except DuplicateKeyError:
            return self.collection.find_one({"_id": job["_id"]})
        return job

    @_guarded
    def latest_for_story(self, story_id: str) -> Optional[dict[str, Any]]:
        """The most recent Job made for a story."""
        return self.collection.find_one({"story_id": story_id}, sort=[("created_at", -1)])

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

    @_guarded
    def save_stage_partial(
        self, job_id: str, stage: str, data: dict[str, Any], worker_id: Optional[str] = None
    ) -> None:
        """Save progress a Stage made before it finished, such as the notebook it created."""
        update = {f"stages.{stage}.partial.{key}": value for key, value in data.items()}
        update["updated_at"] = _now()
        self._write(job_id, {"$set": update}, worker_id)

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
                "$unset": {"error": "", "lease_until": "", "active_fingerprint": ""},
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
            "$unset": {"lease_until": "", "active_fingerprint": ""},
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

    # --- parking: waiting for a login or for the quota, not failing ---------------------------

    @_guarded
    def park_job(
        self,
        job_id: str,
        kind: str,
        stage: str,
        refund_attempt: bool = True,
        worker_id: Optional[str] = None,
    ) -> None:
        """Park a Job. The attempt it had just started on `stage` is given back, so waiting never
        uses up its retries."""
        now = _now()
        update: dict[str, Any] = {
            "$set": {
                "state": kind,
                "step": PARKED_STEPS[kind],
                "error": PARKED_STEPS[kind],
                "parked_at": now,
                "updated_at": now,
                f"stages.{stage}.state": "waiting",
            },
            "$unset": {"lease_until": ""},
        }
        if refund_attempt:
            update["$inc"] = {f"stages.{stage}.attempts": -1}
        self._write(job_id, update, worker_id)

    @_guarded
    def block_service(self, kind: str, message: str, resume_at: Optional[datetime] = None) -> int:
        """Record that NotebookLM cannot be used, and park every waiting Job that still needs it.

        Returns how many Jobs were parked. Jobs that already have their deck do not need
        NotebookLM again, so they are left to carry on.
        """
        now = _now()
        self.flags.update_one(
            {"_id": SERVICE_FLAG_ID},
            {"$set": {"status": kind, "since": now, "resume_at": resume_at, "message": message}},
            upsert=True,
        )
        result = self.collection.update_many(
            {"state": QUEUED, "stages.notebooklm_collect.state": {"$ne": "done"}},
            {
                "$set": {
                    "state": kind,
                    "step": PARKED_STEPS[kind],
                    "error": PARKED_STEPS[kind],
                    "parked_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    @_guarded
    def get_service_flag(self) -> Optional[dict[str, Any]]:
        return self.flags.find_one({"_id": SERVICE_FLAG_ID})

    @_guarded
    def get_session_state(self) -> dict[str, Any]:
        """When the saved login was last checked or used, and when we last told someone about it."""
        return self.flags.find_one({"_id": SESSION_STATE_ID}) or {}

    @_guarded
    def update_session_state(self, **fields: Any) -> None:
        self.flags.update_one({"_id": SESSION_STATE_ID}, {"$set": fields}, upsert=True)

    @_guarded
    def unblock_service(self, kind: str) -> int:
        """NotebookLM can be used again: clear the flag and queue the parked Jobs. Returns how many."""
        now = _now()
        self.flags.delete_one({"_id": SERVICE_FLAG_ID, "status": kind})
        result = self.collection.update_many(
            {"state": kind},
            {
                "$set": {"state": QUEUED, "run_after": now, "step": WAITING_STEP, "updated_at": now},
                "$unset": {"error": "", "parked_at": ""},
            },
        )
        return result.modified_count

    @_guarded
    def parked_counts(self) -> dict[str, int]:
        return {kind: self.collection.count_documents({"state": kind}) for kind in PARKED_STATES}

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
        if job.get("user_id") and job.get("fingerprint"):
            # Back under the duplicate guard, unless the user has meanwhile queued the same request again.
            try:
                self.collection.update_one(
                    {"_id": job_id}, {"$set": {"active_fingerprint": f"{job['user_id']}:{job['fingerprint']}"}}
                )
            except DuplicateKeyError:
                pass
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
