import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.api.jobs import get_job_repository
from app.automation.errors import NeedsLoginError, QuotaExhaustedError
from app.core.config import settings
from app.main import app
from app.services import job_worker, notifier
from app.services.job_repository import NEEDS_LOGIN, JobRepository
from app.services.notifier import desktop_command, notify
from app.services.session_health import session_health

from tests.test_job_parking import Pipeline, enqueue, run
from tests.test_notebooklm_pipeline_steps import FakeContext, NOTEBOOK, flow  # noqa: F401  (flow is a fixture)

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


# --- notifications ----------------------------------------------------------------------------------


def test_desktop_notifications_use_the_systems_own_tool_and_quote_the_text():
    mac = desktop_command('Login "needed"', 'Run `npm run auth` \\ now', "darwin")
    assert mac[:2] == ["osascript", "-e"]
    assert 'with title "Login \\"needed\\""' in mac[2] and "\\\\ now" in mac[2]
    assert desktop_command("T", "M", "linux") == ["notify-send", "T", "M"]
    assert desktop_command("T", "M", "win32") is None


@pytest.fixture
def webhook():
    received = []

    class Handler(BaseHTTPRequestHandler):
        status = 200

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(self.status)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hook", received, Handler
    server.shutdown()


def test_a_webhook_gets_a_json_message_that_slack_and_discord_understand(webhook):
    url, received, _ = webhook
    delivered = notify("NotebookLM login needed", "Run `npm run auth`.", webhook=url, desktop=False)
    assert delivered == ["log", "webhook"]
    body = received[0]
    assert body["title"] == "NotebookLM login needed" and body["message"] == "Run `npm run auth`."
    assert body["text"] == "NotebookLM login needed: Run `npm run auth`."  # Slack
    assert "NotebookLM login needed" in body["content"]  # Discord


def test_the_desktop_channel_runs_the_system_command():
    calls = []
    delivered = notify("T", "M", webhook="", desktop=True, run=lambda command, **kw: calls.append(command))
    assert "desktop" in delivered
    assert len(calls) == 1 and calls[0] == desktop_command("T", "M")  # exactly the system's own command


def test_a_broken_channel_never_raises_and_the_others_still_work(webhook):
    url, received, Handler = webhook
    Handler.status = 500  # the webhook rejects the message

    def boom(*args, **kwargs):
        raise OSError("no notification tool installed")

    delivered = notify("T", "M", webhook=url, desktop=True, run=boom)
    assert delivered == ["log"]  # still logged, nothing raised
    assert notify("T", "M", webhook="http://127.0.0.1:1/never", desktop=False) == ["log"]  # connection refused


def test_with_every_channel_off_it_still_leaves_a_log_line(caplog):
    with caplog.at_level("WARNING"):
        assert notify("Title", "Message", webhook="", desktop=False) == ["log"]
    assert "Title: Message" in caplog.text


# --- how long the saved login lasts ----------------------------------------------------------------------


def write_state(tmp_path, cookies):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")
    return str(path)


def cookie(name, expires_in_days=None, now=NOW):
    return {"name": name, "value": "x", "domain": ".google.com", "expires": (now + timedelta(days=expires_in_days)).timestamp() if expires_in_days is not None else -1}


def test_a_login_with_plenty_of_time_left_is_ok(tmp_path):
    health = session_health(write_state(tmp_path, [cookie("SID", 90), cookie("NID", 5)]), now=NOW, warn_days=3)
    assert health["state"] == "ok" and health["days_left"] == 90  # the soonest Google session cookie counts, not other cookies


def test_a_login_close_to_expiring_is_flagged_so_a_person_can_renew_it_early(tmp_path):
    health = session_health(write_state(tmp_path, [cookie("SID", 2.5), cookie("__Secure-1PSID", 40)]), now=NOW, warn_days=3)
    assert health["state"] == "expiring" and health["days_left"] == 2.5


def test_a_login_that_has_expired(tmp_path):
    health = session_health(write_state(tmp_path, [cookie("SID", -1)]), now=NOW, warn_days=3)
    assert health["state"] == "expired" and health["days_left"] < 0


def test_a_login_made_only_of_session_cookies_has_no_known_end_and_counts_as_ok(tmp_path):
    health = session_health(write_state(tmp_path, [cookie("SID")]), now=NOW)
    assert health == {"state": "ok", "expires_at": None, "days_left": None}


def test_a_missing_or_unusable_login_file(tmp_path):
    assert session_health(str(tmp_path / "nope.json"), now=NOW)["state"] == "missing"
    assert session_health(write_state(tmp_path, [cookie("NID", 30)]), now=NOW)["state"] == "invalid"  # no Google session at all
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    assert session_health(str(bad), now=NOW)["state"] == "invalid"


def test_the_warning_window_is_configurable(tmp_path, monkeypatch):
    path = write_state(tmp_path, [cookie("SID", 6)])
    assert session_health(path, now=NOW)["state"] == "ok"  # default window: 3 days
    monkeypatch.setattr(settings, "NOTEBOOKLM_SESSION_WARN_DAYS", 7)
    assert session_health(path, now=NOW)["state"] == "expiring"


# --- the saved login is refreshed after every good session -----------------------------------------------


@pytest.fixture
def login_file(tmp_path, flow, monkeypatch):  # noqa: F811
    """The flow fixture, with a real login file to refresh and a context that can export its cookies."""
    service, page, browser, calls, source, target = flow
    path = tmp_path / "storage_state.json"
    path.write_text(json.dumps({"cookies": [{"name": "SID", "value": "OLD"}]}), encoding="utf-8")
    monkeypatch.setattr(service, "_storage_state_path", lambda: str(path))

    def storage_state(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"cookies": [{"name": "SID", "value": "REFRESHED"}]}, handle)

    monkeypatch.setattr(FakeContext, "storage_state", storage_state, raising=False)
    return service, page, calls, source, target, path


def saved_value(path):
    return json.loads(path.read_text(encoding="utf-8"))["cookies"][0]["value"]


def test_a_successful_submit_saves_the_refreshed_cookies(login_file):
    service, page, calls, source, target, path = login_file
    service._sync_submit(source, "prompt", target)
    assert saved_value(path) == "REFRESHED"
    assert not (path.parent / "storage_state.json.tmp").exists()  # written to a temp file, then moved into place


def test_a_successful_collect_saves_the_refreshed_cookies(login_file):
    service, page, calls, source, target, path = login_file
    service._sync_collect(NOTEBOOK, target)
    assert saved_value(path) == "REFRESHED"


def test_a_failed_session_leaves_the_saved_login_alone(login_file):
    service, page, calls, source, target, path = login_file

    def broken(p, prompt):
        raise RuntimeError("button vanished")

    service._request_slide_deck = broken
    with pytest.raises(Exception):
        service._sync_submit(source, "prompt", target)
    assert saved_value(path) == "OLD"


def test_a_signed_out_session_never_overwrites_the_saved_login(login_file):
    service, page, calls, source, target, path = login_file
    page.url = "https://accounts.google.com/signin"
    with pytest.raises(NeedsLoginError):
        service._sync_submit(source, "prompt", target)
    assert saved_value(path) == "OLD"


def test_the_refresh_itself_refuses_to_save_a_session_that_has_just_been_signed_out(login_file):
    # Signing out between the last step and the end of the session cannot be caught by a step, so the
    # refresh checks for itself before it writes anything.
    service, page, calls, source, target, path = login_file
    context = FakeContext(None)
    page.url = "https://accounts.google.com/signin"
    service._save_refreshed_login(context, page, str(path), ())
    assert saved_value(path) == "OLD"
    page.url = NOTEBOOK
    service._save_refreshed_login(context, page, str(path), ())
    assert saved_value(path) == "REFRESHED"


def test_a_failing_refresh_keeps_the_old_login_and_does_not_fail_the_job(login_file, monkeypatch):
    service, page, calls, source, target, path = login_file

    def cannot_write(self, path):
        raise OSError("disk full")

    monkeypatch.setattr(FakeContext, "storage_state", cannot_write, raising=False)
    assert service._sync_submit(source, "prompt", target) == NOTEBOOK  # the job still succeeds
    assert saved_value(path) == "OLD"
    assert not (path.parent / "storage_state.json.tmp").exists()


def test_a_session_check_refreshes_the_login_too(login_file):
    service, page, calls, source, target, path = login_file
    assert service._sync_check_session() is True
    assert saved_value(path) == "REFRESHED"


def test_a_session_check_reports_a_signed_out_login(login_file):
    service, page, calls, source, target, path = login_file
    page.url = "https://accounts.google.com/signin"
    assert service._sync_check_session() is False
    assert saved_value(path) == "OLD"


# --- telling a person when jobs have to wait ----------------------------------------------------------------


@pytest.fixture
def repository():
    return JobRepository(mongomock.MongoClient()["sard_care_test"]["jobs"])


class Notices:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def __call__(self, title, message):
        self.sent.append((title, message))
        return ["log"]


def test_the_first_job_to_find_the_login_expired_triggers_one_notification(repository):
    pipe, notices = Pipeline(), Notices()
    pipe.browser_error = NeedsLoginError("expired")
    for index, job_id in enumerate(["a", "b", "c"]):
        enqueue(repository, job_id, at=index)
    run(pipe.worker(repository, notifier=notices))

    (title, message), = notices.sent
    assert title == "NotebookLM login needed"
    assert "npm run auth" in message and "3 job(s) are waiting" in message
    assert "not failed" in message


def test_later_jobs_meeting_the_same_problem_do_not_notify_again(repository):
    pipe, notices = Pipeline(), Notices()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "first")
    worker = pipe.worker(repository, notifier=notices)
    run(worker)
    enqueue(repository, "late")
    run(worker)  # parked straight away, because the problem is already known
    assert len(notices.sent) == 1


def test_two_jobs_hitting_the_same_problem_at_once_notify_only_once(repository):
    # Both were already running when the login expired, so neither was stopped by the flag check.
    pipe, notices = Pipeline(), Notices()
    enqueue(repository, "a", at=0)
    enqueue(repository, "b", at=1)
    worker = pipe.worker(repository, notifier=notices, worker_id="w")
    for _ in range(2):
        assert repository.claim_next("w", 60) is not None

    async def both_fail():
        await worker._park("a", "notebooklm_submit", NeedsLoginError("expired"))
        await worker._park("b", "notebooklm_submit", NeedsLoginError("expired"))

    asyncio.run(both_fail())
    assert repository.get("a")["state"] == NEEDS_LOGIN and repository.get("b")["state"] == NEEDS_LOGIN
    assert len(notices.sent) == 1


def test_a_quota_refusal_after_a_login_problem_is_a_new_problem_and_notifies_again(repository):
    pipe, notices = Pipeline(), Notices()
    enqueue(repository, "a", at=0)
    enqueue(repository, "b", at=1)
    worker = pipe.worker(repository, notifier=notices, worker_id="w")
    for _ in range(2):
        repository.claim_next("w", 60)

    async def two_problems():
        await worker._park("a", "notebooklm_submit", NeedsLoginError("expired"))
        await worker._park("b", "notebooklm_submit", QuotaExhaustedError("daily limit"))

    asyncio.run(two_problems())
    assert [title for title, _ in notices.sent] == ["NotebookLM login needed", "NotebookLM quota reached"]


def test_a_quota_refusal_says_when_the_jobs_will_be_tried_again(repository):
    pipe, notices = Pipeline(), Notices()
    pipe.browser_error = QuotaExhaustedError("daily limit")
    enqueue(repository, "a")
    run(pipe.worker(repository, notifier=notices))
    (title, message), = notices.sent
    assert title == "NotebookLM quota reached" and "will be tried again at 20" in message and "UTC" in message


def test_a_person_is_told_when_the_waiting_jobs_resume(repository):
    pipe, notices = Pipeline(), Notices()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "a")
    since = None
    worker = pipe.worker(repository, notifier=notices, session_time=lambda: since)
    run(worker)
    since = repository.get_service_flag()["since"].replace(tzinfo=timezone.utc) + timedelta(minutes=1)
    pipe.browser_error = None
    assert asyncio.run(worker.resume_if_ready()) == 1
    assert notices.sent[-1] == ("NotebookLM is usable again", "Resumed 1 waiting job(s).")


def test_a_notifier_that_fails_does_not_stop_jobs_from_being_parked(repository):
    pipe = Pipeline()
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "a")

    def broken(title, message):
        raise RuntimeError("webhook exploded")

    run(pipe.worker(repository, notifier=broken))
    assert repository.get("a")["state"] == NEEDS_LOGIN


# --- the periodic check of the saved login -----------------------------------------------------------------------


class Probe:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.result


def health(state, days_left=None):
    return {"state": state, "expires_at": None, "days_left": days_left}


@pytest.fixture
def checking(monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_SESSION_CHECK_HOURS", 12)
    monkeypatch.setattr(job_worker, "session_health", lambda: health("ok"))


def check_worker(repository, probe, notices):
    return Pipeline().worker(repository, session_probe=probe, notifier=notices)


def check(worker):
    return asyncio.run(worker.session_check_if_due())


def test_the_check_is_off_when_the_interval_is_zero(repository, monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_SESSION_CHECK_HOURS", 0)
    probe = Probe()
    assert check(check_worker(repository, probe, Notices())) is None and probe.calls == 0


def test_a_healthy_login_is_checked_and_its_use_recorded(repository, checking):
    probe, notices = Probe(True), Notices()
    assert check(check_worker(repository, probe, notices)) == "ok"
    state = repository.get_session_state()
    assert probe.calls == 1 and state["last_checked_at"] and state["last_ok_at"]
    assert notices.sent == [] and repository.get_service_flag() is None


def test_it_does_not_check_again_until_the_interval_has_passed(repository, checking):
    probe = Probe(True)
    worker = check_worker(repository, probe, Notices())
    check(worker)
    assert check(worker) is None and probe.calls == 1  # too soon
    repository.update_session_state(last_checked_at=datetime.now(timezone.utc) - timedelta(hours=13))
    assert check(worker) == "ok" and probe.calls == 2


def test_a_login_google_has_ended_parks_the_waiting_jobs_and_tells_a_person_before_more_users_submit(repository, checking):
    pipe, notices, probe = Pipeline(), Notices(), Probe(False)
    enqueue(repository, "waiting")
    assert check(pipe.worker(repository, session_probe=probe, notifier=notices)) == "signed_out"

    assert repository.get_service_flag()["status"] == NEEDS_LOGIN
    assert repository.get("waiting")["state"] == NEEDS_LOGIN  # parked, not failed, before any browser stage ran
    (title, message), = notices.sent
    assert title == "NotebookLM login needed" and "npm run auth" in message


@pytest.mark.parametrize("state", ["missing", "invalid", "expired"])
def test_a_login_known_to_be_unusable_is_reported_without_opening_a_browser(repository, monkeypatch, state):
    monkeypatch.setattr(settings, "NOTEBOOKLM_SESSION_CHECK_HOURS", 12)
    monkeypatch.setattr(job_worker, "session_health", lambda: health(state))
    probe, notices = Probe(True), Notices()
    assert check(check_worker(repository, probe, notices)) == state
    assert probe.calls == 0  # nothing to try: the cookies are gone or past their date
    assert repository.get_service_flag()["status"] == NEEDS_LOGIN and len(notices.sent) == 1


def test_a_login_about_to_expire_warns_once_a_day_and_is_still_checked(repository, monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_SESSION_CHECK_HOURS", 12)
    monkeypatch.setattr(job_worker, "session_health", lambda: health("expiring", 2.0))
    probe, notices = Probe(True), Notices()
    worker = check_worker(repository, probe, notices)

    assert check(worker) == "ok"
    assert [title for title, _ in notices.sent] == ["NotebookLM login expires soon"]
    assert "about 2.0 day(s)" in notices.sent[0][1] and "npm run auth" in notices.sent[0][1]

    repository.update_session_state(last_checked_at=datetime.now(timezone.utc) - timedelta(hours=13))
    check(worker)  # twelve hours later is still within the day: no second warning
    assert len(notices.sent) == 1 and probe.calls == 2

    repository.update_session_state(
        last_checked_at=datetime.now(timezone.utc) - timedelta(hours=13),
        last_expiry_alert_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    check(worker)
    assert len(notices.sent) == 2


def test_nothing_is_checked_while_the_login_is_already_known_to_be_needed(repository, checking):
    pipe, notices, probe = Pipeline(), Notices(), Probe(True)
    pipe.browser_error = NeedsLoginError("expired")
    enqueue(repository, "a")
    run(pipe.worker(repository, notifier=notices))
    before = len(notices.sent)
    worker = pipe.worker(repository, session_probe=probe, notifier=notices)
    assert check(worker) == "already_flagged" and probe.calls == 0 and len(notices.sent) == before


def test_the_check_waits_for_its_turn_like_any_other_browser_use(repository, checking):
    probe, notices = Probe(True), Notices()

    async def scenario():
        limiter = asyncio.Semaphore(1)
        worker = Pipeline().worker(repository, session_probe=probe, notifier=notices, browser_limiter=limiter)
        await limiter.acquire()  # a job is using the one allowed browser
        task = asyncio.create_task(worker.session_check_if_due())
        await asyncio.sleep(0.1)
        assert not task.done() and probe.calls == 0
        limiter.release()
        assert await task == "ok" and probe.calls == 1

    asyncio.run(scenario())


# --- what the status endpoint shows -------------------------------------------------------------------------------


def test_the_status_endpoint_shows_the_health_of_the_saved_login(repository, tmp_path, monkeypatch):
    path = write_state(tmp_path, [cookie("SID", 90, now=datetime.now(timezone.utc))])
    monkeypatch.setattr("app.services.notebooklm_service.storage_state_candidates", lambda: [path])
    repository.update_session_state(last_checked_at=NOW, last_ok_at=NOW)
    app.dependency_overrides[get_job_repository] = lambda: repository
    try:
        body = TestClient(app).get("/notebooklm/status").json()
    finally:
        app.dependency_overrides.clear()
    assert body["session"]["state"] == "ok" and 89 < body["session"]["days_left"] < 91
    assert body["session"]["last_checked_at"].startswith("2026-10-06") and body["session"]["last_ok_at"]
