import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.api.jobs import get_job_repository
from app.core.config import settings
from app.main import app
from app.services import pipeline, temp_cleanup
from app.services.job_repository import COMPLETED, DEAD_LETTER, JobRepository
from app.services.job_worker import JobWorker
from app.services.notebooklm_service import NotebookLMService
from app.services.narration_service import NarrationGenerationError

from tests.test_job_queue import story_request
from tests.test_video_pipeline import make_slide, make_tone, request_fixture

LOCAL = "http://127.0.0.1:8000/temp/"


@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TEMP_DIR", str(tmp_path / "temp"))
    (tmp_path / "temp").mkdir()
    return tmp_path / "temp"


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_cleanup_test"]["jobs"])


def make_files(temp_dir, story_id, names):
    for name in names:
        path = temp_dir / story_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 10)


def listing(temp_dir, story_id):
    root = temp_dir / story_id
    if not root.exists():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


RESULT = {
    "presentation_url": "https://cdn.example/deck.pdf",
    "video_url": "https://cdn.example/video.mp4",
    "thumbnail_url": "https://cdn.example/thumb.jpg",
    "narration_audio_url": "https://cdn.example/narration.mp3",
    "scenes": [
        {"image_url": f"{LOCAL}story-1/slides_attempt_1/scene_01.png"},
        {"image_url": f"{LOCAL}story-1/slides_attempt_1/scene_02.png"},
    ],
}

WORK_FILES = [
    "story.md",
    "narration.mp3",
    "narration_segments/scene_01.mp3",
    "narration_segments/scene_02.mp3",
    "audio/slides.concat.txt",
    "video/final_story.mp4",
    "notebooklm_attempt_1/notebooklm_presentation.pdf",
    "notebooklm_attempt_1/notebooklm_artifacts/collect/page.html",
    "slides_attempt_1/scene_01.png",
    "slides_attempt_1/scene_02.png",
    "slides_attempt_1/scene_03.png",
]


# --- trimming a finished job -----------------------------------------------------------------


def test_a_finished_job_keeps_only_the_files_its_result_links_to(temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    removed = temp_cleanup.trim_after_completion("story-1", RESULT)
    assert listing(temp_dir, "story-1") == ["slides_attempt_1/scene_01.png", "slides_attempt_1/scene_02.png"]
    assert removed == len(WORK_FILES) - 2


def test_media_served_from_here_is_kept_media_uploaded_elsewhere_is_not(temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    result = {
        **RESULT,
        "video_url": f"{LOCAL}story-1/video/final_story.mp4",
        "narration_audio_url": f"{LOCAL}story-1/narration.mp3",
        "presentation_url": f"{LOCAL}story-1/notebooklm_attempt_1/notebooklm_presentation.pdf",
    }
    temp_cleanup.trim_after_completion("story-1", result)
    assert listing(temp_dir, "story-1") == [
        "narration.mp3",
        "notebooklm_attempt_1/notebooklm_presentation.pdf",
        "slides_attempt_1/scene_01.png",
        "slides_attempt_1/scene_02.png",
        "video/final_story.mp4",
    ]


def test_empty_folders_left_behind_are_removed(temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    temp_cleanup.trim_after_completion("story-1", RESULT)
    folders = sorted(str(p.relative_to(temp_dir / "story-1")) for p in (temp_dir / "story-1").rglob("*") if p.is_dir())
    assert folders == ["slides_attempt_1"]


def test_trimming_never_touches_another_story(temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    make_files(temp_dir, "story-2", WORK_FILES)
    temp_cleanup.trim_after_completion("story-1", RESULT)
    assert listing(temp_dir, "story-2") == sorted(WORK_FILES)


def test_trimming_a_story_with_no_folder_does_nothing(temp_dir):
    assert temp_cleanup.trim_after_completion("never-ran", RESULT) == 0


# --- an id can never point outside the temp folder ---------------------------------------------


@pytest.mark.parametrize("story_id", ["..", ".", "", "../outside", "a/b", "/etc", "../../etc/passwd", "temp/.."])
def test_unsafe_ids_have_no_folder(temp_dir, story_id):
    assert temp_cleanup.work_dir_path(story_id) is None


def test_nothing_outside_the_temp_folder_is_ever_deleted(temp_dir, tmp_path):
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (temp_dir / "legit").mkdir()

    for story_id in ("../precious", "..", "../../precious"):
        assert temp_cleanup.remove_work_dir(story_id) is False
        assert temp_cleanup.trim_after_completion(story_id, {}) == 0
    assert (outside / "keep.txt").exists()


def test_a_symlink_out_of_the_temp_folder_is_not_followed(temp_dir, tmp_path):
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (temp_dir / "sneaky").symlink_to(outside, target_is_directory=True)
    assert temp_cleanup.work_dir_path("sneaky") is None
    assert temp_cleanup.remove_work_dir("sneaky") is False
    assert (outside / "keep.txt").exists()


def test_a_result_cannot_make_the_cleanup_keep_or_touch_files_elsewhere(temp_dir, tmp_path):
    outside = tmp_path / "precious.txt"
    outside.write_text("keep")
    make_files(temp_dir, "story-1", ["a.txt"])
    result = {"video_url": f"{LOCAL}../precious.txt", "scenes": []}
    temp_cleanup.trim_after_completion("story-1", result)
    assert outside.exists()
    assert listing(temp_dir, "story-1") == []  # the escape attempt kept nothing


# --- the job id sent to the API ------------------------------------------------------------------


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("story_id", ["../../etc", "a/b", "x y", "", "a" * 65, "..", ".hidden"])
def test_the_api_refuses_a_story_id_that_is_not_safe_in_a_path(client, repository, story_id):
    response = client.post("/jobs", json=story_request(story_id))
    assert response.status_code == 422
    assert repository.collection.count_documents({}) == 0


@pytest.mark.parametrize("story_id", ["8f14e45f-ceea-4672-9e24-3f1a8d2b0c11", "story_1", "S-9"])
def test_the_api_accepts_ordinary_ids(client, story_id):
    assert client.post("/jobs", json=story_request(story_id)).status_code == 202


def test_cancelling_a_job_removes_its_working_files(client, repository, temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    client.post("/jobs", json={**story_request("story-1"), "user_id": "u1", "job_id": "j1"})
    response = client.post("/jobs/j1/cancel", json={"user_id": "u1"})
    assert response.status_code == 200
    assert not (temp_dir / "story-1").exists()


def test_a_cancel_that_is_refused_leaves_the_files_alone(client, repository, temp_dir):
    make_files(temp_dir, "story-1", WORK_FILES)
    client.post("/jobs", json={**story_request("story-1"), "user_id": "u1", "job_id": "j1"})
    repository.claim_next("w", 60)  # running now
    assert client.post("/jobs/j1/cancel", json={"user_id": "u1"}).status_code == 409
    assert listing(temp_dir, "story-1") == sorted(WORK_FILES)


# --- the worker, end to end ------------------------------------------------------------------------


def patch_pipeline(monkeypatch, tmp_path, narration_fails=False):
    visuals = []
    for index in range(8):
        path = tmp_path / f"source_scene_{index + 1:02d}.png"
        make_slide(path, index + 1, (320, 180))
        visuals.append(str(path))
    artifact = tmp_path / "notebooklm_presentation.pdf"
    artifact.write_bytes(b"%PDF synthetic" + b"x" * 12_000)

    async def submit(self, file_path, prompt, target_dir, notebook_url=None, on_notebook=None):
        return "https://notebooklm.google.com/notebook/x"

    async def collect(self, notebook_url, target_dir):
        # The real stage downloads into the attempt folder; make that visible to the cleanup.
        os.makedirs(target_dir, exist_ok=True)
        local = os.path.join(target_dir, "notebooklm_presentation.pdf")
        Path(local).write_bytes(artifact.read_bytes())
        return local, True

    async def extract(presentation_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        out = []
        for index, source in enumerate(visuals, start=1):
            target = os.path.join(output_dir, f"scene_{index:02d}.png")
            Path(target).write_bytes(Path(source).read_bytes())
            out.append(target)
        return out

    async def narration(text, voice_gender, output_path, voice_tone=""):
        if narration_fails:
            raise NarrationGenerationError("tts down")
        make_tone(Path(output_path), 0.45)
        return output_path

    async def upload(**kwargs):
        return {"presentation_url": "https://cdn.example/deck.pdf", "video_url": "https://cdn.example/v.mp4",
                "thumbnail_url": "https://cdn.example/t.jpg", "narration_audio_url": "https://cdn.example/n.mp3"}

    for name, value in {
        "TEMP_DIR": str(tmp_path / "temp"), "MIN_SLIDES": 8, "VIDEO_WIDTH": 320, "VIDEO_HEIGHT": 180,
        "VIDEO_FPS": 10, "MIN_SLIDE_DURATION": 0.55, "SLIDE_PADDING": 0.05, "MIN_VIDEO_BYTES": 1000,
        "JOB_RETRY_BACKOFF_SECONDS": (0,),
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(NotebookLMService, "submit", submit)
    monkeypatch.setattr(NotebookLMService, "collect", collect)
    monkeypatch.setattr(pipeline.slide_extractor, "extract_slides", extract)
    monkeypatch.setattr(pipeline.slide_extractor, "extract_slide_texts", lambda path: ["فكرة تعليمية"] * 8)
    monkeypatch.setattr(pipeline.narration_service, "generate_narration", narration)
    monkeypatch.setattr(pipeline.imagekit_uploader, "upload_assets", upload)
    monkeypatch.setattr(pipeline.story_repository, "save_story_record", lambda record: True)


def drain(worker):
    async def go():
        for _ in range(20):
            if not await worker.process_one():
                return

    asyncio.run(go())


def test_a_completed_job_leaves_only_the_scene_images_it_links_to(monkeypatch, tmp_path, repository):
    patch_pipeline(monkeypatch, tmp_path)
    request = request_fixture("clean-story")
    repository.enqueue("clean-story", request.model_dump(), job_id="job")
    drain(JobWorker(repository, poll_interval=0))

    job = repository.get("job")
    assert job["state"] == COMPLETED
    left = listing(tmp_path / "temp", "clean-story")
    assert left == [f"slides_attempt_1/scene_{n:02d}.png" for n in range(1, 9)]
    # Every file the result still links to is really there.
    for scene in job["result"]["scenes"]:
        rel = scene["image_url"][len(LOCAL):]
        assert (tmp_path / "temp" / rel).is_file()


def test_a_job_that_ends_without_a_result_keeps_its_files_for_a_requeue(monkeypatch, tmp_path, repository):
    patch_pipeline(monkeypatch, tmp_path, narration_fails=True)
    request = request_fixture("kept-story")
    repository.enqueue("kept-story", request.model_dump(), job_id="job")
    drain(JobWorker(repository, poll_interval=0))

    assert repository.get("job")["state"] == DEAD_LETTER
    left = listing(tmp_path / "temp", "kept-story")
    assert "story.md" in left
    assert any(name.startswith("notebooklm_attempt_1/") for name in left)
    assert any(name.startswith("slides_attempt_1/") for name in left)


def test_media_the_upload_did_not_return_a_url_for_stays_available_locally(monkeypatch, tmp_path, repository):
    patch_pipeline(monkeypatch, tmp_path)

    async def upload_without_narration(**kwargs):
        return {"presentation_url": "https://cdn.example/deck.pdf", "video_url": "https://cdn.example/v.mp4",
                "thumbnail_url": "https://cdn.example/t.jpg"}

    monkeypatch.setattr(pipeline.imagekit_uploader, "upload_assets", upload_without_narration)
    repository.enqueue("fallback", request_fixture("fallback").model_dump(), job_id="job")
    drain(JobWorker(repository, poll_interval=0))

    job = repository.get("job")
    assert job["result"]["narration_audio_url"].startswith(LOCAL)  # the result links to the local file...
    assert "narration.mp3" in listing(tmp_path / "temp", "fallback")  # ...so the cleanup keeps it


def test_a_cleanup_that_fails_does_not_fail_the_job(monkeypatch, tmp_path, repository):
    patch_pipeline(monkeypatch, tmp_path)

    def boom(story_id, result):
        raise OSError("disk went away")

    monkeypatch.setattr(temp_cleanup, "trim_after_completion", boom)
    repository.enqueue("s", request_fixture("s").model_dump(), job_id="job")
    drain(JobWorker(repository, poll_interval=0))
    assert repository.get("job")["state"] == COMPLETED


# --- purging old files -------------------------------------------------------------------------------


def age(path: Path, days: float):
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def job_ended(repository, job_id, story_id, state, days_ago):
    repository.enqueue(story_id, story_request(story_id), job_id=job_id)
    repository.collection.update_one(
        {"_id": job_id},
        {"$set": {"state": state, "finished_at": datetime.now(timezone.utc) - timedelta(days=days_ago)}},
    )


def test_old_failed_dead_lettered_and_cancelled_jobs_lose_their_files(temp_dir, repository):
    for story_id, state in (("old-failed", "failed"), ("old-dead", "dead_letter"), ("old-cancelled", "cancelled")):
        make_files(temp_dir, story_id, ["story.md"])
        job_ended(repository, f"job-{story_id}", story_id, state, days_ago=8)

    purged = temp_cleanup.purge_stale(repository, retention_days=7)
    assert sorted(purged) == ["old-cancelled", "old-dead", "old-failed"]
    assert os.listdir(temp_dir) == []


def test_recent_failures_are_kept_so_an_admin_can_still_requeue_them(temp_dir, repository):
    make_files(temp_dir, "recent", ["story.md"])
    job_ended(repository, "job-recent", "recent", "dead_letter", days_ago=2)
    assert temp_cleanup.purge_stale(repository, retention_days=7) == []
    assert (temp_dir / "recent").exists()


@pytest.mark.parametrize("state", ["queued", "running", "needs_login", "quota_exhausted", "completed"])
def test_jobs_that_are_waiting_running_or_done_are_never_purged(temp_dir, repository, state):
    make_files(temp_dir, "alive", ["story.md"])
    job_ended(repository, "job-alive", "alive", state, days_ago=30)
    assert temp_cleanup.purge_stale(repository, retention_days=7) == []
    assert (temp_dir / "alive").exists()


def test_folders_no_job_owns_are_purged_only_when_old(temp_dir, repository):
    make_files(temp_dir, "orphan-old", ["a.txt"])
    make_files(temp_dir, "orphan-new", ["a.txt"])
    age(temp_dir / "orphan-old", 10)
    assert temp_cleanup.purge_stale(repository, retention_days=7) == ["orphan-old"]
    assert (temp_dir / "orphan-new").exists()


def test_purge_ignores_loose_files_and_a_missing_temp_folder(temp_dir, repository, monkeypatch):
    (temp_dir / "stray.txt").write_text("x")
    age(temp_dir / "stray.txt", 30)
    assert temp_cleanup.purge_stale(repository, retention_days=7) == []
    assert (temp_dir / "stray.txt").exists()
    monkeypatch.setattr(settings, "TEMP_DIR", str(temp_dir / "does-not-exist"))
    assert temp_cleanup.purge_stale(repository, retention_days=7) == []


def test_retention_defaults_to_the_setting(temp_dir, repository, monkeypatch):
    make_files(temp_dir, "old", ["a.txt"])
    job_ended(repository, "job-old", "old", "failed", days_ago=3)
    monkeypatch.setattr(settings, "JOB_TEMP_RETENTION_DAYS", 2)
    assert temp_cleanup.purge_stale(repository) == ["old"]


def test_the_worker_purges_at_most_once_per_interval(temp_dir, repository, monkeypatch):
    calls = []
    monkeypatch.setattr(temp_cleanup, "purge_stale", lambda repo: calls.append(1) or [])
    monkeypatch.setattr(settings, "JOB_TEMP_PURGE_INTERVAL_SECONDS", 3600)
    worker = JobWorker(repository, poll_interval=0, stages=[])

    async def go():
        for _ in range(5):
            await worker.purge_if_due()

    asyncio.run(go())
    assert len(calls) == 1  # the first poll, then not again for an hour
