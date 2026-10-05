import asyncio
import threading
from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from app.automation.errors import TransientStepError
from app.core.config import settings
from app.services import pipeline
from app.services.job_repository import COMPLETED, JobRepository
from app.services.job_worker import JobWorker
from app.services.notebooklm_service import NotebookLMService
from app.services.pipeline import InsufficientSlidesError, StageSpec

from tests.test_job_lease import SimulatedCrash, expire_lease
from tests.test_job_queue import story_request


class LockedCollection:
    """A collection whose every call holds a lock, so several workers can share mongomock safely."""

    def __init__(self, collection):
        self._collection = collection
        self._lock = threading.RLock()

    def __getattr__(self, name):
        attribute = getattr(self._collection, name)
        if not callable(attribute):
            return attribute

        def locked(*args, **kwargs):
            with self._lock:
                return attribute(*args, **kwargs)

        return locked


@pytest.fixture
def repository():
    return JobRepository(LockedCollection(mongomock.MongoClient()["sard_split_test"]["jobs"]))


@pytest.fixture(autouse=True)
def retries(monkeypatch):
    monkeypatch.setattr(settings, "JOB_STAGE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (0,))
    monkeypatch.setattr(settings, "GENERATION_RETRY_LIMIT", 1)


def enqueue(repository, job_id="job-1", story="story-1"):
    repository.enqueue(story, story_request(story), job_id=job_id)


class FakeNotebookLM:
    """NotebookLM, as far as the Job can tell: it counts notebooks and records what it was asked."""

    def __init__(self):
        self.notebooks_created = 0
        self.submit_calls: list[dict] = []
        self.collect_calls: list[str] = []
        self.deleted: list[str] = []
        self.submit_failures: list[BaseException] = []
        self.collect_failures: list[BaseException] = []

    def install(self, monkeypatch):
        async def submit(service, file_path, prompt, target_dir, notebook_url=None, on_notebook=None):
            self.submit_calls.append({"notebook_url": notebook_url, "target_dir": target_dir, "prompt": prompt})
            if notebook_url is None:
                self.notebooks_created += 1
                notebook_url = f"https://notebooklm.google.com/notebook/nb-{self.notebooks_created}"
                if on_notebook:
                    on_notebook(notebook_url)  # saved before anything else can go wrong
            if self.submit_failures:
                raise self.submit_failures.pop(0)
            return notebook_url

        async def collect(service, notebook_url, target_dir):
            self.collect_calls.append(notebook_url)
            if self.collect_failures:
                raise self.collect_failures.pop(0)
            self.deleted.append(notebook_url)
            return f"{target_dir}/deck.pdf", True

        monkeypatch.setattr(NotebookLMService, "submit", submit)
        monkeypatch.setattr(NotebookLMService, "collect", collect)


def worker_with_fake_rest(repository, worker_id, extract_failures=None, **kwargs):
    """The real Submit and Collect stages followed by instant fake stages."""
    extract_failures = extract_failures if extract_failures is not None else []

    async def extract(ctx):
        if extract_failures:
            raise extract_failures.pop(0)
        return {"slides": 8}

    async def finish(ctx):
        return {"status": "completed"}

    submit_spec, collect_spec = pipeline.STAGES[0], pipeline.STAGES[1]
    stages = [submit_spec, collect_spec, StageSpec("extract_slides", extract, 55, "x"), StageSpec("upload", finish, 90, "x")]
    return JobWorker(repository, poll_interval=0, stages=stages, worker_id=worker_id, **kwargs)


def drain(worker, limit=20):
    async def go():
        runs = 0
        while runs < limit and await worker.process_one():
            runs += 1

    asyncio.run(go())


# --- the stages -----------------------------------------------------------------------------


def test_notebooklm_is_two_stages_and_only_those_use_a_browser():
    assert [spec.name for spec in pipeline.STAGES] == [
        "notebooklm_submit", "notebooklm_collect", "extract_slides", "narrate", "compose", "upload",
    ]
    assert [spec.name for spec in pipeline.STAGES if spec.uses_browser] == ["notebooklm_submit", "notebooklm_collect"]


# --- Submit saves the notebook, retries continue in it -------------------------------------------


def test_the_notebook_url_is_saved_on_the_job_before_submit_finishes(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.submit_failures = [TransientStepError("slide deck control not found")]
    fake.install(monkeypatch)
    enqueue(repository)

    asyncio.run(worker_with_fake_rest(repository, "w").process_one())  # submit fails after creating the notebook

    job = repository.get("job-1")
    assert job["stages"]["notebooklm_submit"]["state"] == "waiting"
    assert job["stages"]["notebooklm_submit"]["partial"]["notebook_url"] == "https://notebooklm.google.com/notebook/nb-1"


def test_a_retried_submit_carries_on_in_the_same_notebook_so_no_second_one_is_created(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.submit_failures = [TransientStepError("x"), TransientStepError("x")]
    fake.install(monkeypatch)
    enqueue(repository)
    drain(worker_with_fake_rest(repository, "w"))

    assert repository.get("job-1")["state"] == COMPLETED
    assert fake.notebooks_created == 1
    assert [call["notebook_url"] for call in fake.submit_calls] == [
        None,
        "https://notebooklm.google.com/notebook/nb-1",
        "https://notebooklm.google.com/notebook/nb-1",
    ]
    assert repository.get("job-1")["stages"]["notebooklm_submit"]["attempts"] == 3


def test_collect_receives_the_notebook_that_submit_made(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.install(monkeypatch)
    enqueue(repository)
    drain(worker_with_fake_rest(repository, "w"))

    job = repository.get("job-1")
    assert job["stages"]["notebooklm_submit"]["output"] == {"notebook_url": "https://notebooklm.google.com/notebook/nb-1"}
    assert fake.collect_calls == ["https://notebooklm.google.com/notebook/nb-1"]
    assert job["stages"]["notebooklm_collect"]["output"]["notebook_deleted"] is True
    assert fake.deleted == ["https://notebooklm.google.com/notebook/nb-1"]


# --- crash during generation ---------------------------------------------------------------------


def test_after_a_crash_during_generation_collect_finds_the_existing_notebook(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.collect_failures = [SimulatedCrash()]
    fake.install(monkeypatch)
    enqueue(repository)

    with pytest.raises(SimulatedCrash):
        asyncio.run(worker_with_fake_rest(repository, "worker-a", lease_seconds=60).process_one())
    job = repository.get("job-1")
    assert job["stages"]["notebooklm_submit"]["state"] == "done"  # the deck had been requested
    assert job["stages"]["notebooklm_collect"]["state"] == "running"

    expire_lease(repository)
    asyncio.run(worker_with_fake_rest(repository, "worker-b", lease_seconds=60).process_one())

    assert repository.get("job-1")["state"] == COMPLETED
    assert fake.notebooks_created == 1  # no second notebook, no second deck request
    assert len(fake.submit_calls) == 1
    assert fake.collect_calls == [
        "https://notebooklm.google.com/notebook/nb-1",
        "https://notebooklm.google.com/notebook/nb-1",
    ]


def test_a_failed_collect_is_retried_in_the_same_notebook_without_submitting_again(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.collect_failures = [TransientStepError("deck not ready in time")]
    fake.install(monkeypatch)
    enqueue(repository)
    drain(worker_with_fake_rest(repository, "w"))

    assert repository.get("job-1")["state"] == COMPLETED
    assert len(fake.submit_calls) == 1
    assert len(fake.collect_calls) == 2


def test_a_deck_that_comes_back_too_short_gets_a_fresh_notebook_and_the_longer_prompt(repository, monkeypatch):
    fake = FakeNotebookLM()
    fake.install(monkeypatch)
    enqueue(repository)
    drain(worker_with_fake_rest(repository, "w", extract_failures=[InsufficientSlidesError(4)]))

    assert repository.get("job-1")["state"] == COMPLETED
    assert fake.notebooks_created == 2
    first, second = fake.submit_calls
    assert second["notebook_url"] is None  # the saved notebook belonged to the first attempt
    assert second["target_dir"].endswith("notebooklm_attempt_2")
    assert second["prompt"] != first["prompt"]


# --- how many browsers ----------------------------------------------------------------------------


def make_counting_stages(browser_stage_seconds=0.05):
    stats = {"browser_now": 0, "browser_max": 0, "other_now": 0, "other_max": 0, "both_max": 0}

    def note():
        stats["both_max"] = max(stats["both_max"], stats["browser_now"] + stats["other_now"])

    async def browser_stage(ctx):
        stats["browser_now"] += 1
        stats["browser_max"] = max(stats["browser_max"], stats["browser_now"])
        note()
        await asyncio.sleep(browser_stage_seconds)
        stats["browser_now"] -= 1
        return {"ok": True}

    async def other_stage(ctx):
        stats["other_now"] += 1
        stats["other_max"] = max(stats["other_max"], stats["other_now"])
        note()
        await asyncio.sleep(browser_stage_seconds)
        stats["other_now"] -= 1
        return {"status": "completed"}

    stages = [
        StageSpec("browser", browser_stage, 20, "x", uses_browser=True),
        StageSpec("other", other_stage, 90, "x"),
    ]
    return stages, stats


def test_browser_sessions_are_capped_by_configuration_whatever_the_worker_count(repository):
    stages, stats = make_counting_stages()

    # The limiter must be created inside the running loop it will be used in.
    async def scenario():
        limiter = asyncio.Semaphore(1)
        for index in range(6):
            enqueue(repository, f"job-{index}", f"story-{index}")
        pool = [JobWorker(repository, poll_interval=0, stages=stages, worker_id=f"w{n}", browser_limiter=limiter) for n in range(3)]

        async def loop(worker):
            while await worker.process_one():
                pass

        await asyncio.gather(*(loop(worker) for worker in pool))

    asyncio.run(scenario())
    assert stats["browser_max"] == 1  # three workers, one browser at a time
    assert all(repository.get(f"job-{index}")["state"] == COMPLETED for index in range(6))


def test_a_higher_cap_allows_that_many_browsers_and_no_more(repository):
    stages, stats = make_counting_stages()

    async def scenario():
        limiter = asyncio.Semaphore(2)
        for index in range(6):
            enqueue(repository, f"job-{index}", f"story-{index}")
        pool = [JobWorker(repository, poll_interval=0, stages=stages, worker_id=f"w{n}", browser_limiter=limiter) for n in range(4)]

        async def loop(worker):
            while await worker.process_one():
                pass

        await asyncio.gather(*(loop(worker) for worker in pool))

    asyncio.run(scenario())
    assert stats["browser_max"] == 2


def test_other_stages_overlap_with_a_jobs_browser_work(repository):
    # One job can narrate and compose while another waits on NotebookLM.
    stages, stats = make_counting_stages(browser_stage_seconds=0.08)

    async def scenario():
        limiter = asyncio.Semaphore(1)
        for index in range(4):
            enqueue(repository, f"job-{index}", f"story-{index}")
        pool = [JobWorker(repository, poll_interval=0, stages=stages, worker_id=f"w{n}", browser_limiter=limiter) for n in range(3)]

        async def loop(worker):
            while await worker.process_one():
                pass

        await asyncio.gather(*(loop(worker) for worker in pool))

    asyncio.run(scenario())
    assert stats["browser_max"] == 1
    assert stats["both_max"] >= 2  # a browser stage and another stage ran at the same time


def test_without_a_limiter_stages_are_not_held_back(repository):
    stages, stats = make_counting_stages()
    enqueue(repository)
    drain(JobWorker(repository, poll_interval=0, stages=stages, worker_id="w"))
    assert repository.get("job-1")["state"] == COMPLETED


def test_defaults_are_one_worker_and_one_browser():
    assert settings.model_fields["JOB_WORKER_CONCURRENCY"].default == 1
    assert settings.model_fields["NOTEBOOKLM_BROWSER_CONCURRENCY"].default == 1


def test_the_app_starts_the_configured_number_of_workers_sharing_one_limiter(monkeypatch):
    import app.api.jobs as jobs_module
    import app.main as main_module
    from fastapi.testclient import TestClient

    created = []

    class SpyWorker:
        def __init__(self, repository, browser_limiter=None, **kwargs):
            created.append(browser_limiter)

        async def run_forever(self):
            await asyncio.sleep(3600)

        def stop(self):
            pass

    monkeypatch.setattr(main_module, "JobWorker", SpyWorker)
    monkeypatch.setattr(jobs_module, "_repository", object())
    monkeypatch.setattr(settings, "JOB_WORKER_CONCURRENCY", 3)
    monkeypatch.setattr(settings, "NOTEBOOKLM_BROWSER_CONCURRENCY", 2)

    with TestClient(main_module.app):
        pass

    assert len(created) == 3
    assert len({id(limiter) for limiter in created}) == 1  # one semaphore shared by every worker
    assert created[0]._value == 2
