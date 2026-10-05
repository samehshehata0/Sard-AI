import asyncio
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api.jobs import get_job_repository
from app.main import app
from app.schemas.story import GeneratedScene, StoryGenerationRequest, StoryGenerationResponse
from app.services.job_repository import (
    COMPLETED,
    FAILED,
    QUEUED,
    RUNNING,
    JobRepository,
    JobStoreUnavailable,
)
from app.services.job_worker import GENERIC_FAILURE, JobWorker


def story_request(story_id="story-1", title="قصة الشمس"):
    return {
        "story_id": story_id,
        "story_title": title,
        "story_idea": "كيف تشرق الشمس",
        "education_level": "المرحلة الابتدائية",
        "story_duration": "تلقائي",
        "learning_objectives": ["فهم دورة النهار"],
        "student_age": "8 سنوات",
        "student_level": "مبتدئ",
        "learning_needs": "لا يوجد",
        "story_style": "رسوم",
        "voice_tone": "ودود",
        "narrator_gender": "female",
        "output_type": "نص + صوت + فيديو",
        "custom_instructions": "",
    }


def completed_response(story_id="story-1"):
    return StoryGenerationResponse(
        story_id=story_id,
        status="completed",
        presentation_url="https://cdn.example/deck.pdf",
        video_url="https://cdn.example/video.mp4",
        duration_seconds=42.0,
        created_at="2026-01-01T00:00:00+00:00",
        scenes=[
            GeneratedScene(
                scene_number=1,
                title="المشهد 1",
                visual_description="v",
                narration_text="n",
                image_url="https://cdn.example/1.png",
                duration_seconds=8,
            )
        ],
    )


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_test"]["jobs"])


# --- repository ------------------------------------------------------------


def test_enqueue_stores_a_queued_job(repository):
    job = repository.enqueue("story-1", story_request(), job_id="job-1")
    stored = repository.get("job-1")
    assert job["_id"] == "job-1"
    assert stored["state"] == QUEUED
    assert stored["story_id"] == "story-1"
    assert stored["request"]["story_title"] == "قصة الشمس"
    assert stored["attempts"] == 0


def test_enqueue_with_the_same_job_id_does_not_create_a_second_job(repository):
    repository.enqueue("story-1", story_request(), job_id="job-1")
    again = repository.enqueue("story-1", story_request(), job_id="job-1")
    assert again["_id"] == "job-1"
    assert repository.collection.count_documents({}) == 1


def test_claim_takes_the_oldest_queued_job_first(repository):
    now = datetime.now(timezone.utc)
    for index, job_id in enumerate(["third", "first", "second"]):
        repository.enqueue(f"s-{job_id}", story_request(), job_id=job_id)
    # Make creation order explicit: first, second, third.
    for offset, job_id in enumerate(["first", "second", "third"]):
        repository.collection.update_one({"_id": job_id}, {"$set": {"created_at": now + timedelta(seconds=offset)}})

    assert [repository.claim_next()["_id"] for _ in range(3)] == ["first", "second", "third"]
    assert repository.claim_next() is None


def test_claim_marks_the_job_running_and_never_hands_it_out_twice(repository):
    repository.enqueue("story-1", story_request(), job_id="job-1")
    claimed = repository.claim_next()
    assert claimed["state"] == RUNNING
    assert claimed["attempts"] == 1
    assert claimed["started_at"] is not None
    assert repository.claim_next() is None


def test_claim_ignores_jobs_that_are_not_due_yet(repository):
    repository.enqueue("story-1", story_request(), job_id="later")
    repository.collection.update_one(
        {"_id": "later"}, {"$set": {"run_after": datetime.now(timezone.utc) + timedelta(hours=1)}}
    )
    assert repository.claim_next() is None


def test_complete_and_fail_record_the_outcome(repository):
    repository.enqueue("s1", story_request("s1"), job_id="ok")
    repository.enqueue("s2", story_request("s2"), job_id="bad")
    repository.complete("ok", {"video_url": "v"})
    repository.fail("bad", "تعذر الإنشاء")
    assert repository.get("ok")["state"] == COMPLETED
    assert repository.get("ok")["result"] == {"video_url": "v"}
    assert repository.get("ok")["progress"] == 100
    assert repository.get("bad")["state"] == FAILED
    assert repository.get("bad")["error"] == "تعذر الإنشاء"


class DownCollection:
    """A collection whose server cannot be reached."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ServerSelectionTimeoutError("mongo is down")

        return fail


def test_mongo_down_is_reported_not_swallowed():
    repository = JobRepository(DownCollection())
    for call in (
        lambda: repository.enqueue("s", story_request()),
        lambda: repository.get("x"),
        lambda: repository.claim_next(),
        lambda: repository.complete("x", {}),
        lambda: repository.fail("x", "e"),
    ):
        with pytest.raises(JobStoreUnavailable):
            call()


# --- worker ----------------------------------------------------------------


def make_worker(repository, runner):
    return JobWorker(repository, runner, poll_interval=0)


def test_worker_with_nothing_queued_does_nothing(repository):
    async def runner(req):
        raise AssertionError("must not run")

    assert asyncio.run(make_worker(repository, runner).process_one()) is False


def test_worker_runs_the_pipeline_and_stores_the_result(repository):
    seen = []

    async def runner(req: StoryGenerationRequest):
        seen.append(req)
        assert repository.get("job-1")["state"] == RUNNING  # visible while it runs
        return completed_response(req.story_id)

    repository.enqueue("story-1", story_request(), job_id="job-1")
    assert asyncio.run(make_worker(repository, runner).process_one()) is True

    job = repository.get("job-1")
    assert job["state"] == COMPLETED
    assert job["result"]["video_url"] == "https://cdn.example/video.mp4"
    assert job["result"]["scenes"][0]["scene_number"] == 1
    assert seen[0].story_title == "قصة الشمس"


def test_worker_records_the_pipelines_arabic_failure_message(repository):
    async def runner(req):
        raise HTTPException(status_code=500, detail="تعذر إنشاء العرض التعليمي عبر NotebookLM. يرجى إعادة المحاولة.")

    repository.enqueue("story-1", story_request(), job_id="job-1")
    asyncio.run(make_worker(repository, runner).process_one())
    job = repository.get("job-1")
    assert job["state"] == FAILED
    assert job["error"].startswith("تعذر إنشاء العرض التعليمي")


def test_worker_turns_an_unexpected_crash_into_a_failed_job(repository):
    async def runner(req):
        raise RuntimeError("boom")

    repository.enqueue("story-1", story_request(), job_id="job-1")
    asyncio.run(make_worker(repository, runner).process_one())
    assert repository.get("job-1")["state"] == FAILED
    assert repository.get("job-1")["error"] == GENERIC_FAILURE


def test_worker_runs_jobs_one_at_a_time_in_order(repository):
    order = []

    async def runner(req):
        order.append(req.story_id)
        return completed_response(req.story_id)

    now = datetime.now(timezone.utc)
    for offset, story_id in enumerate(["a", "b", "c"]):
        repository.enqueue(story_id, story_request(story_id), job_id=f"job-{story_id}")
        repository.collection.update_one({"_id": f"job-{story_id}"}, {"$set": {"created_at": now + timedelta(seconds=offset)}})

    worker = make_worker(repository, runner)

    async def drain():
        while await worker.process_one():
            pass

    asyncio.run(drain())
    assert order == ["a", "b", "c"]


def test_worker_loop_survives_the_job_store_going_down_and_stops_on_request():
    async def runner(req):
        raise AssertionError("no job should run")

    worker = JobWorker(JobRepository(DownCollection()), runner, poll_interval=0)

    async def scenario():
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.05)
        assert not task.done()  # still alive despite the outage
        worker.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


# --- API -------------------------------------------------------------------


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_post_jobs_returns_immediately_with_a_queued_job(client, repository):
    response = client.post("/jobs", json={**story_request(), "job_id": "job-1"})
    assert response.status_code == 202
    body = response.json()
    assert (body["job_id"], body["state"], body["story_id"]) == ("job-1", "queued", "story-1")
    assert repository.get("job-1")["state"] == QUEUED
    assert "request" not in body  # the stored request is not echoed back


def test_post_jobs_without_a_job_id_generates_one(client):
    response = client.post("/jobs", json=story_request())
    assert response.status_code == 202
    assert response.json()["job_id"]


def test_post_jobs_needs_a_story_id(client):
    body = story_request()
    del body["story_id"]
    response = client.post("/jobs", json=body)
    assert response.status_code == 422


def test_post_jobs_rejects_an_invalid_request(client):
    assert client.post("/jobs", json={"story_id": "s"}).status_code == 422


def test_get_job_reports_its_state_and_result(client, repository):
    client.post("/jobs", json={**story_request(), "job_id": "job-1"})
    assert client.get("/jobs/job-1").json()["state"] == "queued"

    asyncio.run(make_worker(repository, lambda req: _async(completed_response(req.story_id))).process_one())
    body = client.get("/jobs/job-1").json()
    assert body["state"] == "completed"
    assert body["progress"] == 100
    assert body["result"]["presentation_url"] == "https://cdn.example/deck.pdf"


async def _async(value):
    return value


def test_get_unknown_job_is_404_in_arabic(client):
    response = client.get("/jobs/nope")
    assert response.status_code == 404
    assert "غير موجودة" in response.json()["detail"]


def test_submission_is_refused_when_mongo_is_down():
    app.dependency_overrides[get_job_repository] = lambda: JobRepository(DownCollection())
    try:
        client = TestClient(app)
        response = client.post("/jobs", json=story_request())
        assert response.status_code == 503
        assert "غير متاحة" in response.json()["detail"]
        assert client.get("/jobs/job-1").status_code == 503
    finally:
        app.dependency_overrides.clear()


# --- the whole thing, as the running app wires it ---------------------------


def wait_for_state(client, job_id, wanted, seconds=5):
    import time

    deadline = time.monotonic() + seconds
    state = None
    while time.monotonic() < deadline:
        state = client.get(f"/jobs/{job_id}").json()["state"]
        if state == wanted:
            return state
        time.sleep(0.05)
    return state


def test_app_worker_picks_up_a_posted_job_and_finishes_it(monkeypatch, repository):
    import app.api.jobs as jobs_module
    import app.main as main_module
    from app.core.config import settings

    async def fake_pipeline(req):
        return completed_response(req.story_id)

    monkeypatch.setattr(jobs_module, "_repository", repository)
    monkeypatch.setattr(main_module, "generate_story", fake_pipeline)
    monkeypatch.setattr(settings, "JOB_POLL_INTERVAL_SECONDS", 0.02)

    with TestClient(app) as client:  # entering the client runs the app's lifespan, which starts the worker
        accepted = client.post("/jobs", json={**story_request("story-e2e"), "job_id": "job-e2e"})
        assert accepted.status_code == 202
        assert wait_for_state(client, "job-e2e", "completed") == "completed"
        body = client.get("/jobs/job-e2e").json()
        assert body["result"]["video_url"] == "https://cdn.example/video.mp4"
        assert body["attempts"] == 1


def test_app_worker_turns_a_pipeline_failure_into_a_failed_job(monkeypatch, repository):
    import app.api.jobs as jobs_module
    import app.main as main_module
    from app.core.config import settings

    async def failing_pipeline(req):
        raise HTTPException(status_code=500, detail="تعذر إنشاء العرض التعليمي عبر NotebookLM. يرجى إعادة المحاولة.")

    monkeypatch.setattr(jobs_module, "_repository", repository)
    monkeypatch.setattr(main_module, "generate_story", failing_pipeline)
    monkeypatch.setattr(settings, "JOB_POLL_INTERVAL_SECONDS", 0.02)

    with TestClient(app) as client:
        client.post("/jobs", json={**story_request("story-bad"), "job_id": "job-bad"})
        assert wait_for_state(client, "job-bad", "failed") == "failed"
        assert "NotebookLM" in client.get("/jobs/job-bad").json()["error"]


def test_the_app_starts_even_though_mongo_is_down(monkeypatch):
    import app.api.jobs as jobs_module
    from app.core.config import settings

    monkeypatch.setattr(jobs_module, "_repository", JobRepository(DownCollection()))
    monkeypatch.setattr(settings, "JOB_POLL_INTERVAL_SECONDS", 0.02)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.post("/jobs", json=story_request()).status_code == 503
