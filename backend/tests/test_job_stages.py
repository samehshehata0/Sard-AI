import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.api.jobs import get_job_repository
from app.automation.errors import (
    NeedsLoginError,
    NotebookLMGenerationError,
    PermanentStepError,
    QuotaExhaustedError,
    TransientStepError,
)
from app.core.config import settings
from app.main import app
from app.services import pipeline
from app.services.job_repository import COMPLETED, DEAD_LETTER, FAILED, QUEUED, JobRepository
from app.services.job_worker import JobWorker, retry_delay_seconds
from app.services.narration_service import NarrationGenerationError
from app.services.notebooklm_service import NotebookLMService
from app.services.pipeline import InsufficientSlidesError, StageSpec

from tests.test_job_queue import story_request


NAMES = ["notebooklm", "extract_slides", "narrate", "compose", "upload"]


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_stage_test"]["jobs"])


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(settings, "JOB_STAGE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (0,))
    monkeypatch.setattr(settings, "GENERATION_RETRY_LIMIT", 1)


class FakeStages:
    """Five stages that record every call and fail on cue. No browser, no media."""

    def __init__(self, plan=None, valid=None):
        self.calls: list[str] = []
        self.expansion_flags: list[bool] = []
        self.plan = {name: list(behaviours) for name, behaviours in (plan or {}).items()}
        self.valid = valid if valid is not None else {}

    def spec(self, name: str) -> StageSpec:
        async def run(ctx):
            self.calls.append(name)
            if name == "notebooklm":
                self.expansion_flags.append(ctx.expansion_retry)
            behaviours = self.plan.get(name, [])
            if behaviours:
                behaviour = behaviours.pop(0)
                if isinstance(behaviour, BaseException):
                    raise behaviour
            if name == "upload":
                return {"status": "completed", "story_id": ctx.story_id}
            return {"stage": name, "run": self.calls.count(name)}

        return StageSpec(
            name,
            run,
            progress=10 * (NAMES.index(name) + 1),
            step=f"step {name}",
            is_valid=lambda ctx, output: self.valid.get(name, True),
        )

    def worker(self, repository) -> JobWorker:
        return JobWorker(repository, poll_interval=0, stages=[self.spec(name) for name in NAMES])


def drain(worker, limit=20):
    async def go():
        runs = 0
        while runs < limit and await worker.process_one():
            runs += 1
        return runs

    return asyncio.run(go())


def enqueue(repository, job_id="job-1"):
    repository.enqueue("story-1", story_request(), job_id=job_id)


# --- the happy path ---------------------------------------------------------


def test_every_stage_runs_once_and_its_output_is_stored(repository):
    stages = FakeStages()
    enqueue(repository)
    drain(stages.worker(repository))

    job = repository.get("job-1")
    assert stages.calls == NAMES
    assert job["state"] == COMPLETED
    assert [name for name, data in job["stages"].items() if data["state"] == "done"] == NAMES
    assert job["stages"]["narrate"]["output"] == {"stage": "narrate", "run": 1}
    assert job["result"] == {"status": "completed", "story_id": "story-1"}
    assert job["progress"] == 100


def test_progress_and_step_follow_the_stage_that_is_running(repository):
    seen = []
    stages = FakeStages()
    original = repository.start_stage

    def spy(job_id, stage, progress, step, **kwargs):
        seen.append((stage, progress, step))
        return original(job_id, stage, progress, step, **kwargs)

    repository.start_stage = spy
    enqueue(repository)
    drain(stages.worker(repository))
    assert seen[0] == ("notebooklm", 10, "step notebooklm")
    assert [stage for stage, _, _ in seen] == NAMES


# --- retry ------------------------------------------------------------------


def test_a_narration_failure_retries_narration_without_repeating_notebooklm(repository):
    stages = FakeStages(plan={"narrate": [TransientStepError("tts down"), TransientStepError("tts down")]})
    enqueue(repository)
    drain(stages.worker(repository))

    job = repository.get("job-1")
    assert job["state"] == COMPLETED
    assert stages.calls.count("notebooklm") == 1
    assert stages.calls.count("extract_slides") == 1
    assert stages.calls.count("narrate") == 3
    assert job["stages"]["narrate"]["attempts"] == 3
    assert job["stages"]["notebooklm"]["attempts"] == 1


def test_a_failed_stage_puts_the_job_back_in_the_queue_with_its_error(repository):
    stages = FakeStages(plan={"narrate": [TransientStepError("tts down")]})
    enqueue(repository)
    assert asyncio.run(stages.worker(repository).process_one()) is True

    job = repository.get("job-1")
    assert job["state"] == QUEUED
    assert job["step"] == "بانتظار إعادة المحاولة..."
    assert job["stages"]["narrate"]["state"] == "waiting"
    assert job["stages"]["extract_slides"]["state"] == "done"  # finished stages are kept
    assert "تعذر" in job["error"]
    assert job["failures"][0]["stage"] == "narrate"
    assert "tts down" in job["failures"][0]["detail"]


def test_retry_waits_longer_each_time(monkeypatch, repository):
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (30, 120, 600))
    stages = FakeStages(plan={"narrate": [TransientStepError("x"), TransientStepError("x")]})
    enqueue(repository)
    worker = stages.worker(repository)

    before = datetime.now(timezone.utc)
    asyncio.run(worker.process_one())
    first = repository.get("job-1")["run_after"]
    assert timedelta(seconds=29) < first.replace(tzinfo=timezone.utc) - before < timedelta(seconds=32)
    assert repository.claim_next() is None  # not due yet

    repository.collection.update_one({"_id": "job-1"}, {"$set": {"run_after": datetime.now(timezone.utc)}})
    before = datetime.now(timezone.utc)
    asyncio.run(worker.process_one())
    second = repository.get("job-1")["run_after"]
    assert timedelta(seconds=119) < second.replace(tzinfo=timezone.utc) - before < timedelta(seconds=122)


def test_backoff_clamps_to_the_last_value(monkeypatch):
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (30, 120, 600))
    assert [retry_delay_seconds(n) for n in (1, 2, 3, 4, 9)] == [30, 120, 600, 600, 600]


def test_a_waiting_job_does_not_block_other_jobs(monkeypatch, repository):
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (3600,))
    stages = FakeStages(plan={"narrate": [TransientStepError("x")]})
    repository.enqueue("story-a", story_request("story-a"), job_id="job-a")
    repository.enqueue("story-b", story_request("story-b"), job_id="job-b")
    repository.collection.update_one({"_id": "job-b"}, {"$set": {"created_at": datetime.now(timezone.utc) + timedelta(seconds=5)}})
    worker = stages.worker(repository)

    asyncio.run(worker.process_one())  # job-a fails at narrate and waits an hour
    asyncio.run(worker.process_one())  # job-b is picked up instead
    assert repository.get("job-a")["state"] == QUEUED
    assert repository.get("job-b")["state"] == COMPLETED


# --- permanent errors and dead letter -----------------------------------------


@pytest.mark.parametrize(
    "error",
    [PermanentStepError("bad"), NeedsLoginError("login"), QuotaExhaustedError("quota"), ValueError("no slides")],
    ids=["permanent", "needs-login", "quota", "value-error"],
)
def test_errors_that_retrying_cannot_fix_are_not_retried(repository, error):
    stages = FakeStages(plan={"compose": [error]})
    enqueue(repository)
    drain(stages.worker(repository))

    job = repository.get("job-1")
    assert job["state"] == FAILED
    assert stages.calls.count("compose") == 1
    assert job["failures"][0]["stage"] == "compose"
    assert job["finished_at"] is not None


def test_a_job_that_uses_every_attempt_goes_to_dead_letter_with_its_evidence(repository):
    errors = []
    for _ in range(3):
        error = TransientStepError("tts down")
        error.evidence_dir = "/tmp/evidence/narrate"
        errors.append(error)
    stages = FakeStages(plan={"narrate": errors})
    enqueue(repository)
    drain(stages.worker(repository))

    job = repository.get("job-1")
    assert job["state"] == DEAD_LETTER
    assert stages.calls.count("narrate") == 3
    assert stages.calls.count("compose") == 0
    assert job["error"].startswith("تعذر")
    assert len(job["failures"]) == 3
    assert {failure["evidence_dir"] for failure in job["failures"]} == {"/tmp/evidence/narrate"}
    assert repository.claim_next() is None  # a dead-lettered job is never picked up again


def test_an_unexpected_crash_is_retried_and_then_dead_lettered(repository):
    stages = FakeStages(plan={"upload": [RuntimeError("boom")] * 3})
    enqueue(repository)
    drain(stages.worker(repository))
    job = repository.get("job-1")
    assert job["state"] == DEAD_LETTER
    assert stages.calls.count("upload") == 3
    assert "RuntimeError: boom" in job["failures"][-1]["detail"]


# --- requeue ------------------------------------------------------------------


def test_an_admin_requeue_resumes_from_the_stage_that_failed(repository):
    stages = FakeStages(plan={"narrate": [TransientStepError("x")] * 3})
    enqueue(repository)
    worker = stages.worker(repository)
    drain(worker)
    assert repository.get("job-1")["state"] == DEAD_LETTER

    assert repository.requeue("job-1") is True
    job = repository.get("job-1")
    assert job["state"] == QUEUED
    assert job["stages"]["narrate"]["attempts"] == 0  # fresh attempts for the stage that failed
    assert "error" not in job

    drain(worker)
    assert repository.get("job-1")["state"] == COMPLETED
    assert stages.calls.count("notebooklm") == 1  # earlier stages were reused
    assert stages.calls.count("extract_slides") == 1


def test_only_failed_or_dead_lettered_jobs_can_be_requeued(repository):
    stages = FakeStages()
    enqueue(repository)
    assert repository.requeue("job-1") is False  # queued
    drain(stages.worker(repository))
    assert repository.requeue("job-1") is False  # completed
    assert repository.requeue("nope") is False


# --- reuse of stored output ----------------------------------------------------


def test_a_stored_output_whose_files_are_gone_is_run_again_along_with_everything_after_it(repository):
    stages = FakeStages(plan={"compose": [TransientStepError("ffmpeg")]})
    enqueue(repository)
    worker = stages.worker(repository)
    asyncio.run(worker.process_one())  # compose fails; narrate output is saved

    stages.valid["narrate"] = False  # e.g. the temp folder was cleaned
    drain(worker)

    assert repository.get("job-1")["state"] == COMPLETED
    assert stages.calls.count("notebooklm") == 1
    assert stages.calls.count("extract_slides") == 1
    assert stages.calls.count("narrate") == 2
    assert stages.calls.count("compose") == 2


# --- a deck that is too short ---------------------------------------------------


def test_a_too_short_deck_asks_notebooklm_again_once_with_the_longer_prompt(repository):
    stages = FakeStages(plan={"extract_slides": [InsufficientSlidesError(4)]})
    enqueue(repository)
    drain(stages.worker(repository))

    assert repository.get("job-1")["state"] == COMPLETED
    assert stages.calls.count("notebooklm") == 2
    assert stages.expansion_flags == [False, True]


def test_a_deck_that_is_still_too_short_fails_for_good(repository):
    stages = FakeStages(plan={"extract_slides": [InsufficientSlidesError(4), InsufficientSlidesError(5)]})
    enqueue(repository)
    drain(stages.worker(repository))

    job = repository.get("job-1")
    assert job["state"] == FAILED
    assert stages.calls.count("notebooklm") == 2
    assert "InsufficientSlidesError" in job["failures"][0]["detail"]


# --- which errors are worth retrying ----------------------------------------------


@pytest.mark.parametrize(
    "error, transient",
    [
        (TransientStepError("x"), True),
        (NotebookLMGenerationError("unclassified"), True),
        (PermanentStepError("x"), False),
        (NeedsLoginError("x"), False),
        (QuotaExhaustedError("x"), False),
        (NarrationGenerationError("tts"), True),
        (RuntimeError("unknown"), True),
        (ValueError("bad input"), False),
    ],
)
def test_which_failures_are_worth_retrying(error, transient):
    assert pipeline.is_transient(error) is transient


# --- admin API ---------------------------------------------------------------------


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


def dead_letter(repository):
    enqueue(repository)
    repository.dead_letter("job-1", "تعذر", "narrate", "TransientStepError: x")


def test_requeue_is_off_unless_an_admin_token_is_configured(client, repository, monkeypatch):
    dead_letter(repository)
    monkeypatch.setattr(settings, "JOB_ADMIN_TOKEN", "")
    assert client.post("/jobs/job-1/requeue", headers={"X-Admin-Token": ""}).status_code == 403
    assert client.post("/jobs/job-1/requeue").status_code == 403


def test_requeue_needs_the_right_token(client, repository, monkeypatch):
    dead_letter(repository)
    monkeypatch.setattr(settings, "JOB_ADMIN_TOKEN", "s3cret")
    assert client.post("/jobs/job-1/requeue").status_code == 403
    assert client.post("/jobs/job-1/requeue", headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert repository.get("job-1")["state"] == DEAD_LETTER


def test_requeue_with_the_token_queues_the_job_again(client, repository, monkeypatch):
    dead_letter(repository)
    monkeypatch.setattr(settings, "JOB_ADMIN_TOKEN", "s3cret")
    response = client.post("/jobs/job-1/requeue", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert response.json()["state"] == "queued"
    assert repository.get("job-1")["state"] == QUEUED


def test_requeue_refuses_unknown_and_unfinished_jobs(client, repository, monkeypatch):
    monkeypatch.setattr(settings, "JOB_ADMIN_TOKEN", "s3cret")
    headers = {"X-Admin-Token": "s3cret"}
    assert client.post("/jobs/nope/requeue", headers=headers).status_code == 404
    enqueue(repository)  # still queued
    assert client.post("/jobs/job-1/requeue", headers=headers).status_code == 409


def test_job_view_shows_stage_progress_but_no_internal_paths(client, repository):
    stages = FakeStages(plan={"narrate": [TransientStepError("x")]})
    enqueue(repository)
    asyncio.run(stages.worker(repository).process_one())
    body = client.get("/jobs/job-1").json()
    assert body["stage"] == "narrate"
    assert body["stages"]["extract_slides"] == {"state": "done", "attempts": 1}
    assert body["stages"]["narrate"]["state"] == "waiting"
    assert "failures" not in body and "request" not in body


# --- the real stages, with fake NotebookLM, narration and upload ----------------------


def test_real_stages_narration_failure_does_not_repeat_notebooklm_or_finished_slides(monkeypatch, tmp_path, repository):
    from tests.test_video_pipeline import make_slide, make_tone, request_fixture

    visuals = []
    for index in range(8):
        path = tmp_path / f"source_scene_{index + 1:02d}.png"
        make_slide(path, index + 1, (320, 180))
        visuals.append(str(path))
    artifact = tmp_path / "notebooklm_presentation.pdf"
    artifact.write_bytes(b"%PDF synthetic" + b"x" * 12_000)

    notebook_runs = []
    collects = []
    narration_calls = []
    failed_once = []

    async def fake_submit(self, file_path, prompt, target_dir, notebook_url=None, on_notebook=None):
        notebook_runs.append(target_dir)
        return "https://notebooklm.google.com/notebook/real-stages"

    async def fake_collect(self, notebook_url, target_dir):
        collects.append(notebook_url)
        return str(artifact), True

    async def fake_extract(presentation_path, output_dir):
        return visuals

    async def fake_narration(text, voice_gender, output_path, voice_tone=""):
        narration_calls.append(Path(output_path).name)
        if output_path.endswith("scene_05.mp3") and not failed_once:
            failed_once.append(True)
            raise NarrationGenerationError("tts hiccup")
        make_tone(Path(output_path), 0.45)
        return output_path

    async def fake_upload(**kwargs):
        return {"presentation_url": "http://local/p.pdf", "video_url": "http://local/v.mp4", "thumbnail_url": "http://local/t.jpg"}

    for name, value in {
        "TEMP_DIR": str(tmp_path / "work"), "MIN_SLIDES": 8, "VIDEO_WIDTH": 320, "VIDEO_HEIGHT": 180,
        "VIDEO_FPS": 10, "MIN_SLIDE_DURATION": 0.55, "SLIDE_PADDING": 0.05, "MIN_VIDEO_BYTES": 1000,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(NotebookLMService, "submit", fake_submit)
    monkeypatch.setattr(NotebookLMService, "collect", fake_collect)
    monkeypatch.setattr(pipeline.slide_extractor, "extract_slides", fake_extract)
    monkeypatch.setattr(pipeline.slide_extractor, "extract_slide_texts", lambda path: ["فكرة تعليمية"] * 8)
    monkeypatch.setattr(pipeline.narration_service, "generate_narration", fake_narration)
    monkeypatch.setattr(pipeline.imagekit_uploader, "upload_assets", fake_upload)
    monkeypatch.setattr(pipeline.story_repository, "save_story_record", lambda record: True)

    request = request_fixture("real-stages").model_dump()
    repository.enqueue("real-stages", request, job_id="job-real")
    drain(JobWorker(repository, poll_interval=0))

    job = repository.get("job-real")
    assert job["state"] == COMPLETED
    assert len(job["result"]["scenes"]) == 8
    assert all(scene["duration_seconds"] > 0 for scene in job["result"]["scenes"])
    assert job["result"]["video_url"] == "http://local/v.mp4"

    assert len(notebook_runs) == 1  # NotebookLM was asked once, despite the narration failure
    assert collects == ["https://notebooklm.google.com/notebook/real-stages"]  # and the deck fetched once
    assert narration_calls[:5] == [f"scene_0{n}.mp3" for n in range(1, 6)]
    # Slides 1-4 were narrated before the failure and not again: 5 tries + slides 5-8 on the retry.
    assert len(narration_calls) == 9
    assert job["stages"]["narrate"]["attempts"] == 2
    assert job["stages"]["notebooklm_submit"]["attempts"] == 1
    assert job["stages"]["notebooklm_collect"]["attempts"] == 1
    assert job["stages"]["notebooklm_collect"]["output"]["notebook_deleted"] is True
