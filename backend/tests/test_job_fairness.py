import asyncio
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.api.jobs import get_job_repository
from app.automation.errors import PermanentStepError
from app.core.config import settings
from app.main import app
from app.services.job_repository import (
    CANCELLED,
    COMPLETED,
    FAILED,
    QUEUED,
    RUNNING,
    JobRepository,
    UserJobLimitReached,
    fingerprint,
)
from app.services.job_worker import JobWorker

from tests.test_job_queue import story_request
from tests.test_job_stages import NAMES, FakeStages


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_fairness_test"]["jobs"])


@pytest.fixture(autouse=True)
def limits(monkeypatch):
    monkeypatch.setattr(settings, "JOB_MAX_ACTIVE_PER_USER", 2)
    monkeypatch.setattr(settings, "JOB_STAGE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (0,))


def submit(repository, user="user-1", story="story-1", title="قصة الشمس", job_id=None):
    return repository.submit(story, story_request(story, title), user_id=user, job_id=job_id or f"job-{story}")


# --- the fingerprint -------------------------------------------------------------------


def test_the_same_story_request_has_the_same_fingerprint_whatever_its_ids():
    a = story_request("story-a")
    b = story_request("story-b")
    b["job_id"] = "some-job"
    assert fingerprint(a) == fingerprint(b)


def test_stray_whitespace_and_empty_optional_fields_do_not_change_the_fingerprint():
    a = story_request()
    b = story_request()
    b["story_title"] = "  قصة   الشمس \n"
    b["custom_instructions"] = None  # the web app sends "" where the schema defaults to None
    assert fingerprint(a) == fingerprint(b)


def test_a_different_request_has_a_different_fingerprint():
    assert fingerprint(story_request(title="قصة الشمس")) != fingerprint(story_request(title="قصة القمر"))
    other = story_request()
    other["learning_objectives"] = ["هدف مختلف"]
    assert fingerprint(story_request()) != fingerprint(other)


# --- duplicates --------------------------------------------------------------------------


def test_submitting_the_same_story_twice_queues_it_once(repository):
    first, first_duplicate = submit(repository, story="story-1", job_id="job-1")
    second, second_duplicate = submit(repository, story="story-2", job_id="job-2")

    assert first_duplicate is False and second_duplicate is True
    assert second["_id"] == "job-1"  # the existing job comes back
    assert repository.collection.count_documents({}) == 1


def test_the_same_story_from_another_user_is_not_a_duplicate(repository):
    submit(repository, user="user-1", story="s1", job_id="j1")
    _, duplicate = submit(repository, user="user-2", story="s2", job_id="j2")
    assert duplicate is False
    assert repository.collection.count_documents({}) == 2


def test_a_different_story_from_the_same_user_is_not_a_duplicate(repository):
    submit(repository, story="s1", title="قصة الشمس", job_id="j1")
    _, duplicate = submit(repository, story="s2", title="قصة القمر", job_id="j2")
    assert duplicate is False


def test_two_submissions_arriving_at_the_same_moment_still_queue_one_job(repository, monkeypatch):
    # Both submissions see "no existing job" and both try to insert: the unique index lets only one in.
    submit(repository, story="s1", job_id="j1")
    real_find_one = repository.collection.find_one
    calls = {"count": 0}

    def blind_first_lookup(query=None, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None  # the racing request has not yet seen the other one
        return real_find_one(query, *args, **kwargs)

    monkeypatch.setattr(repository.collection, "find_one", blind_first_lookup)
    job, duplicate = submit(repository, story="s2", job_id="j2")

    assert duplicate is True
    assert job["_id"] == "j1"
    assert repository.collection.count_documents({}) == 1


def test_a_finished_job_no_longer_blocks_the_same_request(repository):
    job, _ = submit(repository, story="s1", job_id="j1")
    repository.claim_next("w", lease_seconds=60)
    repository.complete("j1", {"ok": True})

    again, duplicate = submit(repository, story="s2", job_id="j2")
    assert duplicate is False and again["_id"] == "j2"


@pytest.mark.parametrize("finish", ["fail", "dead_letter", "cancel"])
def test_failed_dead_lettered_and_cancelled_jobs_do_not_block_a_resubmission(repository, finish):
    submit(repository, story="s1", job_id="j1")
    if finish == "cancel":
        assert repository.cancel("j1", "user-1") == "cancelled"
    else:
        repository.claim_next("w", lease_seconds=60)
        getattr(repository, finish)("j1", "تعذر", "narrate") if finish == "dead_letter" else repository.fail("j1", "تعذر")
    _, duplicate = submit(repository, story="s2", job_id="j2")
    assert duplicate is False


def test_a_job_waiting_to_retry_still_blocks_a_duplicate(repository):
    submit(repository, story="s1", job_id="j1")
    repository.claim_next("w", lease_seconds=60)
    repository.schedule_retry("j1", "narrate", "تعذر", datetime.now(timezone.utc))  # back in the queue
    assert submit(repository, story="s2", job_id="j2")[1] is True


def test_requeueing_a_failed_job_puts_it_back_under_the_duplicate_guard(repository):
    submit(repository, story="s1", job_id="j1")
    repository.claim_next("w", lease_seconds=60)
    repository.fail("j1", "تعذر", "narrate")
    assert repository.requeue("j1") is True
    assert submit(repository, story="s2", job_id="j2")[1] is True


# --- the per-user limit ----------------------------------------------------------------------


def test_a_user_can_have_two_active_jobs_but_not_three(repository):
    submit(repository, story="s1", title="الأولى", job_id="j1")
    submit(repository, story="s2", title="الثانية", job_id="j2")
    with pytest.raises(UserJobLimitReached) as raised:
        submit(repository, story="s3", title="الثالثة", job_id="j3")
    assert (raised.value.active, raised.value.limit) == (2, 2)
    assert repository.collection.count_documents({}) == 2


def test_running_jobs_count_toward_the_limit(repository):
    submit(repository, story="s1", title="الأولى", job_id="j1")
    submit(repository, story="s2", title="الثانية", job_id="j2")
    repository.claim_next("w", lease_seconds=60)  # one is now running, one queued
    with pytest.raises(UserJobLimitReached):
        submit(repository, story="s3", title="الثالثة", job_id="j3")


def test_a_finished_job_frees_a_slot(repository):
    submit(repository, story="s1", title="الأولى", job_id="j1")
    submit(repository, story="s2", title="الثانية", job_id="j2")
    repository.claim_next("w", lease_seconds=60)
    repository.complete("j1", {"ok": True})
    assert submit(repository, story="s3", title="الثالثة", job_id="j3")[1] is False


def test_another_users_jobs_do_not_count(repository):
    submit(repository, user="user-1", story="s1", title="الأولى", job_id="j1")
    submit(repository, user="user-1", story="s2", title="الثانية", job_id="j2")
    assert submit(repository, user="user-2", story="s3", title="الثالثة", job_id="j3")[1] is False


def test_the_limit_is_configurable(monkeypatch, repository):
    monkeypatch.setattr(settings, "JOB_MAX_ACTIVE_PER_USER", 1)
    submit(repository, story="s1", title="الأولى", job_id="j1")
    with pytest.raises(UserJobLimitReached):
        submit(repository, story="s2", title="الثانية", job_id="j2")


def test_a_duplicate_is_reported_before_the_limit_is_checked(repository):
    submit(repository, story="s1", title="الأولى", job_id="j1")
    submit(repository, story="s2", title="الثانية", job_id="j2")
    _, duplicate = submit(repository, story="s3", title="الأولى", job_id="j3")  # same as the first
    assert duplicate is True


def test_without_a_user_there_are_no_rules(repository):
    for index in range(4):
        job, duplicate = repository.submit(f"s{index}", story_request("s"), user_id=None, job_id=f"j{index}")
        assert duplicate is False
    assert repository.collection.count_documents({}) == 4


# --- FIFO ------------------------------------------------------------------------------------


def test_jobs_run_in_the_order_they_were_submitted_across_users(repository):
    now = datetime.now(timezone.utc)
    order = [("user-a", "s1"), ("user-b", "s2"), ("user-a", "s3"), ("user-c", "s4"), ("user-b", "s5")]
    for offset, (user, story) in enumerate(order):
        submit(repository, user=user, story=story, title=f"قصة {story}", job_id=f"job-{story}")
        repository.collection.update_one({"_id": f"job-{story}"}, {"$set": {"created_at": now + timedelta(seconds=offset)}})

    stages = FakeStages()
    started = []
    original_start = repository.start_stage

    def spy(job_id, stage, progress, step, **kwargs):
        if stage == "notebooklm":
            started.append(job_id)
        return original_start(job_id, stage, progress, step, **kwargs)

    repository.start_stage = spy
    worker = JobWorker(repository, poll_interval=0, stages=[stages.spec(n) for n in NAMES])

    async def drain():
        while await worker.process_one():
            pass

    asyncio.run(drain())
    assert started == [f"job-{story}" for _, story in order]


def test_a_user_with_many_old_jobs_does_not_jump_the_queue(repository):
    now = datetime.now(timezone.utc)
    submit(repository, user="busy", story="s1", title="الأولى", job_id="busy-1")
    submit(repository, user="busy", story="s2", title="الثانية", job_id="busy-2")
    submit(repository, user="other", story="s3", title="الثالثة", job_id="other-1")
    for offset, job_id in enumerate(["busy-1", "busy-2", "other-1"]):
        repository.collection.update_one({"_id": job_id}, {"$set": {"created_at": now + timedelta(seconds=offset)}})
    assert [repository.claim_next("w", 60)["_id"] for _ in range(3)] == ["busy-1", "busy-2", "other-1"]


# --- cancel ------------------------------------------------------------------------------------


def test_a_user_can_cancel_a_queued_job(repository):
    submit(repository, story="s1", job_id="j1")
    assert repository.cancel("j1", "user-1") == "cancelled"
    job = repository.get("j1")
    assert job["state"] == CANCELLED
    assert job["error"] == "أُلغي طلب التوليد."
    assert job["finished_at"] is not None
    assert repository.claim_next("w", 60) is None  # a cancelled job is never run


def test_a_running_job_cannot_be_cancelled(repository):
    submit(repository, story="s1", job_id="j1")
    repository.claim_next("w", 60)
    assert repository.cancel("j1", "user-1") == "not_cancellable"
    assert repository.get("j1")["state"] == RUNNING


@pytest.mark.parametrize("state", [COMPLETED, FAILED, CANCELLED])
def test_a_finished_job_cannot_be_cancelled(repository, state):
    submit(repository, story="s1", job_id="j1")
    repository.collection.update_one({"_id": "j1"}, {"$set": {"state": state}})
    assert repository.cancel("j1", "user-1") == "not_cancellable"


def test_only_the_owner_can_cancel(repository):
    submit(repository, user="user-1", story="s1", job_id="j1")
    assert repository.cancel("j1", "user-2") == "forbidden"
    assert repository.get("j1")["state"] == QUEUED
    assert repository.cancel("missing", "user-1") == "not_found"


def test_a_job_waiting_for_a_retry_can_be_cancelled(repository):
    submit(repository, story="s1", job_id="j1")
    repository.claim_next("w", 60)
    repository.schedule_retry("j1", "narrate", "تعذر", datetime.now(timezone.utc) + timedelta(hours=1))
    assert repository.cancel("j1", "user-1") == "cancelled"


def test_cancelling_frees_the_users_slot(repository):
    submit(repository, story="s1", title="الأولى", job_id="j1")
    submit(repository, story="s2", title="الثانية", job_id="j2")
    repository.cancel("j1", "user-1")
    assert submit(repository, story="s3", title="الثالثة", job_id="j3")[1] is False


# --- API -----------------------------------------------------------------------------------------


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


def post_job(client, user="user-1", story="story-1", title="قصة الشمس", job_id=None):
    body = {**story_request(story, title), "user_id": user}
    if job_id:
        body["job_id"] = job_id
    return client.post("/jobs", json=body)


def test_a_new_job_is_accepted_with_202(client):
    response = post_job(client, job_id="j1")
    assert response.status_code == 202
    assert response.json()["job_id"] == "j1" and "duplicate" not in response.json()


def test_a_duplicate_comes_back_as_200_with_the_existing_job(client):
    post_job(client, story="s1", job_id="j1")
    response = post_job(client, story="s2", job_id="j2")
    assert response.status_code == 200
    body = response.json()
    assert (body["job_id"], body["story_id"], body["duplicate"]) == ("j1", "s1", True)


def test_going_over_the_limit_is_a_429_with_a_clear_arabic_message(client):
    post_job(client, story="s1", title="الأولى")
    post_job(client, story="s2", title="الثانية")
    response = post_job(client, story="s3", title="الثالثة")
    assert response.status_code == 429
    assert "الحد الأقصى" in response.json()["detail"]
    assert "(2)" in response.json()["detail"]


def test_cancel_endpoint_cancels_a_queued_job(client, repository):
    post_job(client, job_id="j1")
    response = client.post("/jobs/j1/cancel", json={"user_id": "user-1"})
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    assert repository.get("j1")["state"] == CANCELLED


def test_cancel_endpoint_refuses_a_running_job_in_arabic(client, repository):
    post_job(client, job_id="j1")
    repository.claim_next("w", 60)
    response = client.post("/jobs/j1/cancel", json={"user_id": "user-1"})
    assert response.status_code == 409
    assert "قيد التنفيذ" in response.json()["detail"]
    assert repository.get("j1")["state"] == RUNNING


def test_cancel_endpoint_refuses_other_users_and_unknown_jobs(client):
    post_job(client, job_id="j1")
    assert client.post("/jobs/j1/cancel", json={"user_id": "user-2"}).status_code == 403
    assert client.post("/jobs/nope/cancel", json={"user_id": "user-1"}).status_code == 404
    assert client.post("/jobs/j1/cancel", json={}).status_code == 422


def test_cancel_endpoint_refuses_a_finished_job(client, repository):
    post_job(client, job_id="j1")
    repository.claim_next("w", 60)
    repository.complete("j1", {"ok": True})
    response = client.post("/jobs/j1/cancel", json={"user_id": "user-1"})
    assert response.status_code == 409
    assert "انتهت" in response.json()["detail"]


def test_a_job_without_a_user_still_works_for_internal_callers(client):
    body = story_request("s9")
    response = client.post("/jobs", json=body)
    assert response.status_code == 202
