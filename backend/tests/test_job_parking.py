import asyncio
import logging
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.api.jobs import get_job_repository
from app.automation.errors import NeedsLoginError, QuotaExhaustedError
from app.core.config import settings
from app.main import app
from app.services.job_repository import (
    CANCELLED,
    COMPLETED,
    NEEDS_LOGIN,
    QUEUED,
    QUOTA_EXHAUSTED,
    JobRepository,
    JobStoreUnavailable,
)
from app.services.job_worker import JobWorker, quota_resume_at
from app.services.pipeline import StageSpec

from tests.test_job_lease import expire_lease
from tests.test_job_queue import story_request


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_parking_test"]["jobs"])


@pytest.fixture(autouse=True)
def settings_for_tests(monkeypatch):
    monkeypatch.setattr(settings, "JOB_STAGE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (0,))
    monkeypatch.setattr(settings, "NOTEBOOKLM_QUOTA_RESET_UTC", "")
    monkeypatch.setattr(settings, "NOTEBOOKLM_QUOTA_PROBE_MINUTES", 60)
    monkeypatch.setattr(settings, "JOB_MAX_ACTIVE_PER_USER", 2)


class Pipeline:
    """Submit, Collect, narrate and upload, with the two browser Stages able to fail on cue."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (job story id, stage)
        self.browser_error: BaseException | None = None  # raised by every browser Stage until cleared

    def spec(self, name: str, uses_browser: bool = False) -> StageSpec:
        async def run(ctx):
            self.calls.append((ctx.story_id, name))
            if uses_browser and self.browser_error is not None:
                raise self.browser_error
            if name == "upload":
                return {"status": "completed", "story_id": ctx.story_id}
            return {"stage": name}

        return StageSpec(name, run, 10, name, uses_browser=uses_browser)

    def worker(self, repository, session_time=None, worker_id="w", **kwargs) -> JobWorker:
        stages = [
            self.spec("notebooklm_submit", True),
            self.spec("notebooklm_collect", True),
            self.spec("narrate"),
            self.spec("upload"),
        ]
        return JobWorker(
            repository,
            poll_interval=0,
            stages=stages,
            worker_id=worker_id,
            session_checker=lambda: session_time() if callable(session_time) else session_time,
            **kwargs,
        )

    def browser_calls(self):
        return [call for call in self.calls if call[1] in ("notebooklm_submit", "notebooklm_collect")]


def enqueue(repository, job_id, story=None, at=0):
    story = story or f"story-{job_id}"
    repository.enqueue(story, story_request(story), job_id=job_id)
    repository.collection.update_one(
        {"_id": job_id}, {"$set": {"created_at": datetime.now(timezone.utc) + timedelta(seconds=at)}}
    )


def run(worker):
    return asyncio.run(worker.process_one())


def drain(worker, limit=30):
    async def go():
        runs = 0
        while runs < limit and await worker.process_one():
            runs += 1

    asyncio.run(go())


def stage_attempts(repository, job_id, stage):
    return repository.get(job_id)["stages"].get(stage, {}).get("attempts", 0)


# --- an expired login parks the jobs --------------------------------------------------------------


def test_an_expired_login_parks_the_job_instead_of_failing_it(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("NotebookLM authentication session expired")
    enqueue(repository, "j1")
    run(pipe.worker(repository))

    job = repository.get("j1")
    assert job["state"] == NEEDS_LOGIN
    assert "تسجيل الدخول" in job["step"]
    assert "finished_at" not in job and "failures" not in job  # not a failure
    assert repository.claim_next("w") is None  # parked jobs are not picked up
    assert repository.get_service_flag()["status"] == NEEDS_LOGIN


def test_parking_gives_the_attempt_back_so_waiting_never_uses_up_retries(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "j1")
    run(pipe.worker(repository))
    assert stage_attempts(repository, "j1", "notebooklm_submit") == 0


def test_every_waiting_job_that_still_needs_notebooklm_is_parked_at_once(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    for index, job_id in enumerate(["a", "b", "c"]):
        enqueue(repository, job_id, at=index)
    # d already has its deck, so it does not need NotebookLM again and must be left alone.
    enqueue(repository, "d", at=3)
    repository.collection.update_one({"_id": "d"}, {"$set": {"stages.notebooklm_collect.state": "done"}})

    run(pipe.worker(repository))  # job a finds out

    assert [repository.get(job_id)["state"] for job_id in "abcd"] == [NEEDS_LOGIN, NEEDS_LOGIN, NEEDS_LOGIN, QUEUED]
    assert repository.parked_counts() == {NEEDS_LOGIN: 3, QUOTA_EXHAUSTED: 0}


def test_a_job_that_arrives_later_is_parked_without_opening_a_browser(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "first")
    run(pipe.worker(repository))
    assert len(pipe.browser_calls()) == 1  # the one that found out

    enqueue(repository, "late")
    run(pipe.worker(repository))

    assert repository.get("late")["state"] == NEEDS_LOGIN
    assert len(pipe.browser_calls()) == 1  # no second browser just to meet the login page again
    assert stage_attempts(repository, "late", "notebooklm_submit") == 0


def test_stages_that_need_no_browser_keep_running_while_the_login_is_expired(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "stuck", at=0)
    run(pipe.worker(repository))  # sets the flag

    enqueue(repository, "has-deck", at=1)
    repository.collection.update_one(
        {"_id": "has-deck"},
        {"$set": {"stages.notebooklm_submit": {"state": "done", "output": {"notebook_url": "u"}, "attempts": 1},
                  "stages.notebooklm_collect": {"state": "done", "output": {"presentation_path": "p"}, "attempts": 1}}},
    )
    # Its earlier stages are "done" but their files do not exist here; treat them as valid for this test.
    worker = pipe.worker(repository)
    for spec in worker.stages:
        object.__setattr__(spec, "is_valid", lambda ctx, output: True)
    run(worker)
    assert repository.get("has-deck")["state"] == COMPLETED


def test_the_log_tells_a_person_what_to_do(repository, caplog):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "a")
    enqueue(repository, "b", at=1)
    with caplog.at_level(logging.ERROR):
        run(pipe.worker(repository))
    assert "LOGIN EXPIRED" in caplog.text
    assert "npm run auth" in caplog.text
    assert "1 other waiting job" in caplog.text


# --- resuming after a login ----------------------------------------------------------------------


def parked_login_jobs(repository, pipe, count=3):
    pipe.browser_error = NeedsLoginError("expired")
    for index in range(count):
        enqueue(repository, f"job-{index}", at=index)
    run(pipe.worker(repository))
    assert repository.parked_counts()[NEEDS_LOGIN] == count
    return repository.get_service_flag()["since"].replace(tzinfo=timezone.utc)


def test_jobs_stay_parked_until_the_login_file_is_newer_than_the_flag(repository):
    pipe = Pipeline()
    since = parked_login_jobs(repository, pipe)

    for stale in (since - timedelta(minutes=5), since, None):  # an old login, the same moment, no file at all
        worker = pipe.worker(repository, session_time=stale)
        assert asyncio.run(worker.resume_if_ready()) == 0
    assert repository.parked_counts()[NEEDS_LOGIN] == 3
    assert repository.get_service_flag() is not None


def test_jobs_resume_by_themselves_after_npm_run_auth(repository, caplog):
    pipe = Pipeline()
    since = parked_login_jobs(repository, pipe)
    pipe.browser_error = None  # the login works again

    worker = pipe.worker(repository, session_time=since + timedelta(minutes=1))
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(worker.resume_if_ready()) == 3

    assert repository.get_service_flag() is None
    assert [repository.get(f"job-{n}")["state"] for n in range(3)] == [QUEUED, QUEUED, QUEUED]
    assert "resumed 3 parked job" in caplog.text
    drain(worker)
    assert all(repository.get(f"job-{n}")["state"] == COMPLETED for n in range(3))


def test_the_worker_loop_resumes_parked_jobs_on_its_own(repository):
    pipe = Pipeline()
    since = parked_login_jobs(repository, pipe, count=2)
    pipe.browser_error = None
    clock = {"saved": since - timedelta(minutes=1)}  # nobody has logged in yet
    worker = pipe.worker(repository, session_time=lambda: clock["saved"])

    async def scenario():
        task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.1)
        assert repository.parked_counts()[NEEDS_LOGIN] == 2  # still waiting
        clock["saved"] = since + timedelta(minutes=1)  # `npm run auth` writes the login file
        for _ in range(100):
            if all(repository.get(f"job-{n}")["state"] == COMPLETED for n in range(2)):
                break
            await asyncio.sleep(0.05)
        worker.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert all(repository.get(f"job-{n}")["state"] == COMPLETED for n in range(2))


def test_a_login_that_is_still_bad_parks_the_jobs_again_and_waits_for_a_newer_file(repository):
    pipe = Pipeline()
    since = parked_login_jobs(repository, pipe, count=1)
    first_login = since + timedelta(minutes=1)

    worker = pipe.worker(repository, session_time=first_login)
    assert asyncio.run(worker.resume_if_ready()) == 1
    run(worker)  # the login file changed but is still no good
    assert repository.get("job-0")["state"] == NEEDS_LOGIN
    # The flag now dates from this second failure, which is after the login file that turned out to be bad.
    # Let an hour pass so that, as in real life, the bad file is older than the flag.
    new_since = repository.get_service_flag()["since"].replace(tzinfo=timezone.utc) + timedelta(hours=1)
    repository.flags.update_one({"_id": "notebooklm"}, {"$set": {"since": new_since}})

    assert asyncio.run(worker.resume_if_ready()) == 0  # the same file does not trigger another loop
    assert asyncio.run(pipe.worker(repository, session_time=new_since + timedelta(minutes=1)).resume_if_ready()) == 1


def test_many_outages_never_use_up_a_jobs_retries(repository):
    pipe = Pipeline()
    enqueue(repository, "j1")
    clock = {"saved": datetime.now(timezone.utc) - timedelta(days=1)}
    worker = pipe.worker(repository, session_time=lambda: clock["saved"])

    for _ in range(6):  # far more outages than the 3 attempts a stage is allowed
        pipe.browser_error = NeedsLoginError("expired")
        run(worker)
        assert repository.get("j1")["state"] == NEEDS_LOGIN
        clock["saved"] = datetime.now(timezone.utc) + timedelta(seconds=1)
        asyncio.run(worker.resume_if_ready())
        clock["saved"] += timedelta(minutes=1)

    pipe.browser_error = None
    drain(worker)
    job = repository.get("j1")
    assert job["state"] == COMPLETED
    assert stage_attempts(repository, "j1", "notebooklm_submit") == 1  # only the try that worked
    assert "failures" not in job


# --- quota ---------------------------------------------------------------------------------------


def test_a_quota_refusal_parks_the_jobs_until_the_reset_time(repository):
    pipe = Pipeline()
    pipe.browser_error = QuotaExhaustedError("daily limit")
    enqueue(repository, "a")
    enqueue(repository, "b", at=1)
    before = datetime.now(timezone.utc)
    run(pipe.worker(repository))

    assert [repository.get(job_id)["state"] for job_id in "ab"] == [QUOTA_EXHAUSTED, QUOTA_EXHAUSTED]
    assert "الحد اليومي" in repository.get("a")["step"]
    assert stage_attempts(repository, "a", "notebooklm_submit") == 0
    resume_at = repository.get_service_flag()["resume_at"].replace(tzinfo=timezone.utc)
    assert timedelta(minutes=59) < resume_at - before < timedelta(minutes=61)  # probing hourly until the reset time is known


def test_quota_jobs_resume_when_the_reset_time_has_passed(repository):
    pipe = Pipeline()
    pipe.browser_error = QuotaExhaustedError("daily limit")
    enqueue(repository, "a")
    run(pipe.worker(repository))
    pipe.browser_error = None
    worker = pipe.worker(repository)

    assert asyncio.run(worker.resume_if_ready()) == 0  # not yet
    assert repository.get("a")["state"] == QUOTA_EXHAUSTED

    repository.flags.update_one({"_id": "notebooklm"}, {"$set": {"resume_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert asyncio.run(worker.resume_if_ready()) == 1
    drain(worker)
    assert repository.get("a")["state"] == COMPLETED


def test_a_quota_that_has_not_really_reset_parks_the_jobs_again(repository):
    pipe = Pipeline()
    pipe.browser_error = QuotaExhaustedError("daily limit")
    enqueue(repository, "a")
    worker = pipe.worker(repository)
    run(worker)
    repository.flags.update_one({"_id": "notebooklm"}, {"$set": {"resume_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    asyncio.run(worker.resume_if_ready())
    run(worker)  # still refused
    assert repository.get("a")["state"] == QUOTA_EXHAUSTED
    assert repository.get_service_flag()["resume_at"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)


@pytest.mark.parametrize(
    "now, reset, expected",
    [
        (datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc), "08:00", datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc), "08:00", datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc), "08:00", datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 10, 5, 23, 59, tzinfo=timezone.utc), "00:00", datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)),
        (datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc), "", datetime(2026, 10, 5, 10, 30, tzinfo=timezone.utc)),
    ],
    ids=["before-reset", "after-reset", "exactly-at-reset", "midnight", "unknown-reset-probes-hourly"],
)
def test_when_a_quota_refusal_is_tried_again(monkeypatch, now, reset, expected):
    monkeypatch.setattr(settings, "NOTEBOOKLM_QUOTA_RESET_UTC", reset)
    assert quota_resume_at(now) == expected


# --- parked jobs are still the user's jobs ------------------------------------------------------------


def test_a_parked_job_still_counts_toward_the_users_limit_and_blocks_a_duplicate(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    repository.submit("s1", story_request("s1", "الأولى"), user_id="user-1", job_id="j1")
    repository.submit("s2", story_request("s2", "الثانية"), user_id="user-1", job_id="j2")
    run(pipe.worker(repository))
    assert repository.get("j1")["state"] == NEEDS_LOGIN

    from app.services.job_repository import UserJobLimitReached

    with pytest.raises(UserJobLimitReached):
        repository.submit("s3", story_request("s3", "الثالثة"), user_id="user-1", job_id="j3")
    _, duplicate = repository.submit("s9", story_request("s9", "الأولى"), user_id="user-1", job_id="j9")
    assert duplicate is True


def test_a_parked_job_can_be_cancelled(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    repository.submit("s1", story_request("s1"), user_id="user-1", job_id="j1")
    run(pipe.worker(repository))
    assert repository.cancel("j1", "user-1") == "cancelled"
    assert repository.get("j1")["state"] == CANCELLED
    asyncio.run(pipe.worker(repository).resume_if_ready())  # resuming must not bring a cancelled job back
    assert repository.get("j1")["state"] == CANCELLED


# --- the flag, visible to a person --------------------------------------------------------------------


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_status_is_ok_when_nothing_is_wrong(client):
    body = client.get("/notebooklm/status").json()
    assert body["status"] == "ok"
    assert body["parked_jobs"] == {NEEDS_LOGIN: 0, QUOTA_EXHAUSTED: 0}
    assert body["action"] is None


def test_status_says_when_a_login_is_needed_and_how_many_jobs_wait(client, repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("NotebookLM authentication session expired")
    enqueue(repository, "a")
    enqueue(repository, "b", at=1)
    run(pipe.worker(repository))
    body = client.get("/notebooklm/status").json()
    assert body["status"] == NEEDS_LOGIN
    assert body["parked_jobs"][NEEDS_LOGIN] == 2
    assert "npm run auth" in body["action"]
    assert body["since"] is not None and "expired" in body["message"]


def test_status_reports_the_quota_and_when_it_will_be_tried_again(client, repository):
    pipe = Pipeline()
    pipe.browser_error = QuotaExhaustedError("daily limit")
    enqueue(repository, "a")
    run(pipe.worker(repository))
    body = client.get("/notebooklm/status").json()
    assert body["status"] == QUOTA_EXHAUSTED
    assert body["resume_at"] is not None


def test_a_parked_job_shows_its_state_and_arabic_step_through_the_job_api(client, repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "a")
    run(pipe.worker(repository))
    body = client.get("/jobs/a").json()
    assert body["state"] == NEEDS_LOGIN
    assert "تسجيل الدخول" in body["step"]


def test_status_is_503_when_mongo_is_down(client):
    from pymongo.errors import ServerSelectionTimeoutError

    class Down:
        """A collection (and its database) whose server cannot be reached."""

        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise ServerSelectionTimeoutError("down")

            return fail

        database = {"service_state": None}

        def __init__(self):
            self.database = {"service_state": self}

    app.dependency_overrides[get_job_repository] = lambda: JobRepository(Down())
    assert TestClient(app).get("/notebooklm/status").status_code == 503
