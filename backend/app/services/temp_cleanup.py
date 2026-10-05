"""Clearing out a Job's working files once they are no longer needed.

A finished Job keeps only the files its result links to: the scene images (and any media that is
served from here rather than uploaded) are fetched through `/temp/...` later, so they stay. A
failed or dead-lettered Job keeps everything, because requeueing it reuses the files, and is
purged after a retention period instead.
"""
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings
from app.services.job_repository import CANCELLED, DEAD_LETTER, FAILED, JobRepository


logger = logging.getLogger(__name__)

# How the app refers to files it serves itself (see the /temp route in main.py).
LOCAL_URL_PREFIX = "http://127.0.0.1:8000/temp/"


def _base() -> str:
    return os.path.realpath(settings.TEMP_DIR)


def work_dir_path(story_id: str) -> Optional[str]:
    """The Job's folder, or None if the id would point anywhere but straight inside the temp folder."""
    if not story_id or story_id in (".", ".."):
        return None
    base = _base()
    target = os.path.realpath(os.path.join(base, story_id))
    return target if os.path.dirname(target) == base else None


def referenced_files(result: dict[str, Any]) -> set[str]:
    """Files inside the temp folder that the result links to."""
    urls = [
        result.get("presentation_url"),
        result.get("video_url"),
        result.get("thumbnail_url"),
        result.get("narration_audio_url"),
        *[scene.get("image_url") for scene in result.get("scenes", [])],
    ]
    base = _base()
    files = set()
    for url in urls:
        if isinstance(url, str) and url.startswith(LOCAL_URL_PREFIX):
            path = os.path.realpath(os.path.join(base, url[len(LOCAL_URL_PREFIX):]))
            if path.startswith(base + os.sep):
                files.add(path)
    return files


def trim_after_completion(story_id: str, result: dict[str, Any]) -> int:
    """Delete everything in a finished Job's folder that its result does not link to. Returns files removed."""
    work_dir = work_dir_path(story_id)
    if work_dir is None or not os.path.isdir(work_dir):
        return 0

    keep = referenced_files(result)
    removed = 0
    for folder, _dirs, files in os.walk(work_dir, topdown=False):
        for name in files:
            path = os.path.realpath(os.path.join(folder, name))
            if path not in keep:
                try:
                    os.remove(os.path.join(folder, name))
                    removed += 1
                except OSError as exc:
                    logger.warning("[Sard] Could not remove %s: %s", path, exc)
        try:
            os.rmdir(folder)  # only succeeds when nothing is left in it
        except OSError:
            pass
    logger.info("[Sard][%s] Cleaned up %s temporary file(s); kept %s", story_id, removed, len(keep))
    return removed


def remove_work_dir(story_id: str) -> bool:
    """Delete a Job's whole folder, for example when it was cancelled."""
    work_dir = work_dir_path(story_id)
    if work_dir is None or not os.path.isdir(work_dir):
        return False
    shutil.rmtree(work_dir, ignore_errors=True)
    return True


def purge_stale(
    repository: JobRepository,
    retention_days: Optional[float] = None,
    now: Optional[datetime] = None,
) -> list[str]:
    """Delete the folders of Jobs that ended without a result a long time ago, and of folders no Job owns.

    Failed, dead-lettered and cancelled Jobs keep their files for `retention_days` so that an admin can
    requeue them. Completed Jobs keep what their result links to, and running or waiting Jobs keep everything.
    """
    base = _base()
    if not os.path.isdir(base):
        return []
    retention = timedelta(days=settings.JOB_TEMP_RETENTION_DAYS if retention_days is None else retention_days)
    now = now or datetime.now(timezone.utc)
    cutoff = now - retention

    purged = []
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if not os.path.isdir(path) or work_dir_path(name) is None:
            continue

        job = repository.latest_for_story(name)
        if job is None:
            ended = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)  # nobody owns this folder
        elif job["state"] in (FAILED, DEAD_LETTER, CANCELLED):
            ended = job.get("finished_at") or job.get("updated_at") or now
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=timezone.utc)
        else:
            continue

        if ended < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            purged.append(name)
            logger.info("[Sard][%s] Purged old working files", name)
    return purged
