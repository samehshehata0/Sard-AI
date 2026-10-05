import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from app.core.config import settings
from app.services.job_repository import (
    COMPLETED,
    DEAD_LETTER,
    QUEUED,
    RUNNING,
    JobRepository,
    LeaseLost,
)
from app.services.job_worker import Heartbeat, JobWorker
from app.services.pipeline import StageSpec

from tests.test_job_queue import story_request
from tests.test_job_stages import NAMES, FakeStages


class SimulatedCrash(BaseException):
    """The worker process dying: nothing in the worker may catch it and tidy up."""


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_lease_test"]["jobs"])


@pytest.fixture(autouse=True)
def retries(monkeypatch):
    monkeypatch.setattr(settings, "JOB_STAGE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "JOB_RETRY_BACKOFF_SECONDS", (0,))


def enqueue(repository, job_id="job-1"):
    repository.enqueue("story-1", story_request(), job_id=job_id)


def expire_lease(repository, job_id="job-1"):
    repository.collection.update_one(
        {"_id": job_id}, {"$set": {"lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}}
    )


def worker_for(repository, stages, worker_id, **kwargs):
    return JobWorker(repository, poll_interval=0, stages=stages, worker_id=worker_id, **kwargs)


def run(worker):
    return asyncio.run(worker.process_one())


# --- claiming and leases -----------------------------------------------------------


def test_a_claim_leases_the_job_to_the_worker(repository):
    enqueue(repository)
    before = datetime.now(timezone.utc)
    job = repository.claim_next("worker-a", lease_seconds=90)
    assert (job["state"], job["worker_id"]) == (RUNNING, "worker-a")
    lease = job["lease_until"].replace(tzinfo=timezone.utc)
    assert timedelta(seconds=88) < lease - before < timedelta(seconds=92)


def test_lease_length_defaults_to_the_setting(monkeypatch, repository):
    monkeypatch.setattr(settings, "JOB_LEASE_SECONDS", 45)
    enqueue(repository)
    job = repository.claim_next("worker-a")
    assert timedelta(seconds=43) < job["lease_until"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) < timedelta(seconds=46)


def test_a_job_with_a_live_lease_is_not_claimed_by_anyone_else(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    assert repository.claim_next("worker-b", lease_seconds=60) is None


def test_a_job_whose_lease_ran_out_is_taken_over(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    expire_lease(repository)

    taken = repository.claim_next("worker-b", lease_seconds=60)
    assert taken["worker_id"] == "worker-b"
    assert taken["_recovered"] is True
    assert (taken["attempts"], taken["takeovers"]) == (2, 1)
    assert "_recovered" not in repository.get("job-1")  # a signal for the caller, never stored


def test_queued_jobs_are_taken_before_abandoned_ones(repository):
    enqueue(repository, "abandoned")
    repository.claim_next("worker-a", lease_seconds=60)
    expire_lease(repository, "abandoned")
    enqueue(repository, "fresh")
    repository.collection.update_one({"_id": "fresh"}, {"$set": {"created_at": datetime.now(timezone.utc) + timedelta(seconds=9)}})
    assert repository.claim_next("worker-b")["_id"] == "fresh"
    assert repository.claim_next("worker-b")["_id"] == "abandoned"


class CallLog:
    """Wraps a collection and records which methods the repository calls on it."""

    def __init__(self, collection):
        self._collection = collection
        self.calls: list[str] = []

    def __getattr__(self, name):
        attribute = getattr(self._collection, name)
        if not callable(attribute):
            return attribute

        def wrapper(*args, **kwargs):
            self.calls.append(name)
            return attribute(*args, **kwargs)

        return wrapper


def test_a_claim_is_one_atomic_find_and_update_never_a_find_followed_by_an_update(repository):
    # MongoDB makes find_one_and_update atomic, which is what stops two workers taking the same Job.
    # mongomock does not lock across threads, so a thread race cannot be tested here; this checks that
    # the claim does not do a separate read and write, which would be racy on any database.
    enqueue(repository)
    log = CallLog(repository.collection)
    repository.collection = log

    assert repository.claim_next("worker-a", lease_seconds=60) is not None
    assert log.calls == ["find_one_and_update"]

    log.calls.clear()
    assert repository.claim_next("worker-b", lease_seconds=60) is None
    assert set(log.calls) == {"find_one_and_update"}  # queued, then expired leases: still no separate read


def test_claims_in_a_row_never_hand_out_the_same_job_twice(repository):
    for index in range(25):
        enqueue(repository, f"job-{index}")
    claimed = []
    for turn in range(40):
        job = repository.claim_next(f"worker-{turn % 4}", lease_seconds=60)
        if job is not None:
            claimed.append(job["_id"])
    assert sorted(claimed) == sorted(f"job-{index}" for index in range(25))


# --- heartbeat ------------------------------------------------------------------------


def test_a_heartbeat_extends_the_lease(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=1)
    assert repository.heartbeat("job-1", "worker-a", lease_seconds=300) is True
    lease = repository.get("job-1")["lease_until"].replace(tzinfo=timezone.utc)
    assert lease - datetime.now(timezone.utc) > timedelta(seconds=290)


def test_a_heartbeat_from_a_worker_that_no_longer_holds_the_job_is_refused(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    expire_lease(repository)
    repository.claim_next("worker-b", lease_seconds=60)
    assert repository.heartbeat("job-1", "worker-a") is False
    assert repository.heartbeat("job-1", "worker-b") is True
    assert repository.heartbeat("nope", "worker-a") is False


def test_the_heartbeat_thread_keeps_refreshing_and_notices_a_lost_job(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    beat = Heartbeat(repository, "job-1", "worker-a", lease_seconds=60, interval=0.02)
    beat.start()
    time.sleep(0.1)
    assert beat.lost is False
    repository.collection.update_one({"_id": "job-1"}, {"$set": {"worker_id": "worker-b"}})
    time.sleep(0.1)
    beat.stop()
    assert beat.lost is True


def test_heartbeat_is_never_slower_than_a_third_of_the_lease(repository):
    assert worker_for(repository, [], "w", lease_seconds=3, heartbeat_seconds=10).heartbeat_seconds == 1
    assert worker_for(repository, [], "w", lease_seconds=300, heartbeat_seconds=20).heartbeat_seconds == 20


def test_lease_and_heartbeat_come_from_settings_by_default(monkeypatch, repository):
    monkeypatch.setattr(settings, "JOB_LEASE_SECONDS", 90)
    monkeypatch.setattr(settings, "JOB_HEARTBEAT_SECONDS", 15)
    worker = JobWorker(repository, stages=[])
    assert (worker.lease_seconds, worker.heartbeat_seconds) == (90, 15)


def test_each_worker_gets_its_own_id(repository):
    assert JobWorker(repository, stages=[]).worker_id != JobWorker(repository, stages=[]).worker_id


# --- fencing -----------------------------------------------------------------------------


def test_a_worker_that_lost_the_job_cannot_write_to_it(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    expire_lease(repository)
    repository.claim_next("worker-b", lease_seconds=60)

    writes = [
        lambda: repository.start_stage("job-1", "narrate", 65, "s", worker_id="worker-a"),
        lambda: repository.save_stage_output("job-1", "narrate", {"x": 1}, worker_id="worker-a"),
        lambda: repository.schedule_retry("job-1", "narrate", "e", datetime.now(timezone.utc), worker_id="worker-a"),
        lambda: repository.reset_stages("job-1", ["narrate"], worker_id="worker-a"),
        lambda: repository.complete("job-1", {"x": 1}, worker_id="worker-a"),
        lambda: repository.fail("job-1", "e", "narrate", worker_id="worker-a"),
        lambda: repository.dead_letter("job-1", "e", "narrate", worker_id="worker-a"),
    ]
    for write in writes:
        with pytest.raises(LeaseLost):
            write()

    job = repository.get("job-1")
    assert (job["state"], job["worker_id"]) == (RUNNING, "worker-b")
    assert "stages" not in job and "failures" not in job

    repository.save_stage_output("job-1", "narrate", {"x": 1}, worker_id="worker-b")  # the owner still can
    assert repository.get("job-1")["stages"]["narrate"]["output"] == {"x": 1}


def test_release_hands_the_job_back_at_once_but_only_for_its_owner(repository):
    enqueue(repository)
    repository.claim_next("worker-a", lease_seconds=60)
    assert repository.release("job-1", "worker-b") is False
    assert repository.release("job-1", "worker-a") is True
    job = repository.get("job-1")
    assert job["state"] == QUEUED and "lease_until" not in job
    assert repository.claim_next("worker-b") is not None


# --- crash recovery ------------------------------------------------------------------------


def test_a_worker_dies_mid_job_and_another_worker_finishes_it(repository):
    crashing = FakeStages(plan={"narrate": [SimulatedCrash()]})
    enqueue(repository)

    with pytest.raises(SimulatedCrash):
        run(worker_for(repository, [crashing.spec(n) for n in NAMES], "worker-a", lease_seconds=60))

    job = repository.get("job-1")
    assert job["state"] == RUNNING  # nobody tidied up: that is what a crash looks like
    assert job["stages"]["extract_slides"]["state"] == "done"
    assert job["stages"]["narrate"]["state"] == "running"
    assert not [t for t in threading.enumerate() if t.name.startswith("heartbeat-")]  # the dead worker stops beating

    expire_lease(repository)  # time passes with no heartbeat
    survivor = FakeStages()
    assert run(worker_for(repository, [survivor.spec(n) for n in NAMES], "worker-b", lease_seconds=60)) is True

    job = repository.get("job-1")
    assert job["state"] == COMPLETED
    assert job["worker_id"] == "worker-b"
    assert job["takeovers"] == 1
    assert crashing.calls == ["notebooklm", "extract_slides", "narrate"]
    assert survivor.calls == ["narrate", "compose", "upload"]  # earlier stages were not repeated
    assert job["stages"]["narrate"]["attempts"] == 2  # the lost try counts


def test_a_job_that_keeps_killing_its_workers_is_dead_lettered(repository):
    enqueue(repository)
    plans = []
    for number in range(3):
        stages = FakeStages(plan={"narrate": [SimulatedCrash()]})
        plans.append(stages)
        with pytest.raises(SimulatedCrash):
            run(worker_for(repository, [stages.spec(n) for n in NAMES], f"worker-{number}", lease_seconds=60))
        expire_lease(repository)

    final = FakeStages()
    run(worker_for(repository, [final.spec(n) for n in NAMES], "worker-last", lease_seconds=60))

    job = repository.get("job-1")
    assert job["state"] == DEAD_LETTER
    assert "narrate" not in final.calls  # not tried a fourth time
    assert "3 times" in job["failures"][-1]["detail"]


def test_a_healthy_slow_job_keeps_its_lease_even_when_the_event_loop_is_blocked(repository):
    probes: list = []
    stop = threading.Event()
    running = threading.Event()

    async def blocking_stage(ctx):
        running.set()  # the worker holds the job now, so the intruder only comes after
        time.sleep(0.8)  # like ffmpeg run synchronously: nothing on the event loop can run meanwhile
        return {"done": True}

    def probe():
        running.wait(timeout=5)
        while not stop.is_set():
            probes.append(repository.claim_next("intruder", lease_seconds=60))
            time.sleep(0.02)

    enqueue(repository)
    worker = worker_for(
        repository, [StageSpec("slow", blocking_stage, 10, "slow")], "worker-a", lease_seconds=0.3, heartbeat_seconds=0.05
    )
    thread = threading.Thread(target=probe)
    thread.start()
    try:
        run(worker)
    finally:
        stop.set()
        thread.join()

    assert repository.get("job-1")["state"] == COMPLETED
    assert repository.get("job-1")["worker_id"] == "worker-a"
    assert probes and all(job is None for job in probes)  # the lease never lapsed


def test_a_worker_that_was_replaced_abandons_the_job_without_overwriting_the_new_owner(repository):
    async def stage(ctx):
        # While this worker is busy, the job is handed to someone else (its lease lapsed).
        repository.collection.update_one({"_id": "job-1"}, {"$set": {"worker_id": "worker-b"}})
        time.sleep(0.3)  # long enough for a heartbeat to notice
        return {"late": True}

    enqueue(repository)
    worker = worker_for(
        repository, [StageSpec("only", stage, 10, "only")], "worker-a", lease_seconds=0.3, heartbeat_seconds=0.05
    )
    assert run(worker) is True

    job = repository.get("job-1")
    assert job["state"] == RUNNING and job["worker_id"] == "worker-b"
    assert job["stages"]["only"].get("output") is None  # the zombie's result was not written
    assert "result" not in job


def test_a_worker_that_is_shut_down_gives_its_job_back_immediately(repository):
    async def scenario():
        gate = asyncio.Event()

        async def waiting_stage(ctx):
            gate.set()
            await asyncio.sleep(30)
            return {}

        enqueue(repository)
        worker = worker_for(repository, [StageSpec("only", waiting_stage, 10, "only")], "worker-a", lease_seconds=600)
        task = asyncio.create_task(worker.process_one())
        await gate.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    job = repository.get("job-1")
    assert job["state"] == QUEUED  # not stuck running until a 10 minute lease runs out
    assert repository.claim_next("worker-b") is not None
