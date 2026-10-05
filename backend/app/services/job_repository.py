import logging
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import settings


logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"

RUNNING_STEP = "جارٍ أتمتة Google NotebookLM وإنشاء العرض التقديمي والشرائح..."


class JobStoreUnavailable(RuntimeError):
    """MongoDB could not be reached. Jobs are never kept in memory instead."""


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
    def claim_next(self) -> Optional[dict[str, Any]]:
        """Atomically take the oldest due queued Job and mark it running."""
        now = _now()
        return self.collection.find_one_and_update(
            {"state": QUEUED, "run_after": {"$lte": now}},
            {
                "$set": {"state": RUNNING, "progress": 25, "step": RUNNING_STEP, "started_at": now, "updated_at": now},
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )

    @_guarded
    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        now = _now()
        self.collection.update_one(
            {"_id": job_id},
            {"$set": {"state": COMPLETED, "progress": 100, "result": result, "finished_at": now, "updated_at": now}},
        )

    @_guarded
    def fail(self, job_id: str, error: str) -> None:
        now = _now()
        self.collection.update_one(
            {"_id": job_id},
            {"$set": {"state": FAILED, "error": error, "finished_at": now, "updated_at": now}},
        )


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
        "error": job.get("error"),
        "result": job.get("result"),
        "created_at": iso(job.get("created_at")),
        "started_at": iso(job.get("started_at")),
        "finished_at": iso(job.get("finished_at")),
    }
