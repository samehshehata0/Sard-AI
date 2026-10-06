import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.automation.errors import NeedsLoginError, TransientStepError
from app.services import notebooklm_service
from app.services.browser_host import BrowserHost
from app.services.notebooklm_service import NotebookLMService, get_browser_host


# --- a fake Playwright --------------------------------------------------------------------------------


class FakePage:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, storage_state):
        self.storage_state = storage_state
        self.pages: list[FakePage] = []
        self.closed = False

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, options):
        self.options = options
        self.connected = True
        self.contexts: list[FakeContext] = []
        self.closed = False

    def is_connected(self):
        return self.connected

    def new_context(self, storage_state, viewport):
        context = FakeContext(storage_state)
        self.contexts.append(context)
        return context

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, world):
        self.world = world
        self.stopped = False
        self.chromium = self

    def launch(self, **options):
        if self.world.launch_error:
            raise self.world.launch_error
        browser = FakeBrowser(options)
        self.world.browsers.append(browser)
        return browser

    def stop(self):
        self.stopped = True


class World:
    """Everything the fake Playwright was asked to do, and the knobs a test can turn."""

    def __init__(self, tmp_path):
        self.browsers: list[FakeBrowser] = []
        self.playwrights: list[FakePlaywright] = []
        self.launch_error = None
        self.login_path = str(tmp_path / "storage_state.json")
        self.login_time = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.now = 0.0
        self.headless = True
        self.recycle_hours = 12.0
        self.has_login = True

    def start(self):
        playwright = FakePlaywright(self)
        self.playwrights.append(playwright)
        return playwright

    def host(self) -> BrowserHost:
        return BrowserHost(
            storage_path=lambda: self.login_path if self.has_login else None,
            login_modified_at=lambda: self.login_time,
            headless=lambda: self.headless,
            recycle_hours=lambda: self.recycle_hours,
            start_playwright=self.start,
            clock=lambda: self.now,
        )


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


@pytest.fixture
def host(world):
    host = world.host()
    yield host
    host.close(timeout=5)


def visit(host):
    """One operation: open a tab, return it."""

    def op():
        with host.page() as page:
            return page

    return host.run_sync(op)


# --- one browser for many operations --------------------------------------------------------------------


def test_many_operations_share_one_browser_and_each_gets_a_fresh_tab_that_is_closed_afterwards(host, world):
    pages = [visit(host) for _ in range(5)]
    assert host.launches == 1 and len(world.browsers) == 1
    assert len({id(page) for page in pages}) == 5  # a new tab every time
    assert all(page.closed for page in pages)  # and none left open
    assert world.browsers[0].closed is False  # while the browser stays open


def test_the_tab_is_closed_even_when_the_operation_fails(host, world):
    seen = []

    def op():
        with host.page() as page:
            seen.append(page)
            raise RuntimeError("the step failed")

    with pytest.raises(RuntimeError, match="the step failed"):
        host.run_sync(op)
    assert seen[0].closed is True
    assert visit(host)  # and the host is still usable
    assert host.launches == 1


def test_the_browser_is_opened_with_the_saved_login_and_the_current_headless_setting(host, world):
    world.headless = False
    visit(host)
    browser = world.browsers[0]
    assert browser.options["headless"] is False
    assert "--no-sandbox" in browser.options["args"]
    assert browser.contexts[0].storage_state == world.login_path


# --- all browser work happens on one thread, one operation at a time ------------------------------------------


def test_every_operation_runs_on_the_one_dedicated_browser_thread(host):
    names = []
    callers = []

    def op():
        names.append(threading.current_thread().name)

    def caller():
        callers.append(threading.current_thread().name)
        host.run_sync(op)

    threads = [threading.Thread(target=caller, name=f"caller-{n}") for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert set(names) == {"notebooklm-browser"}
    assert len(callers) == 4 and "notebooklm-browser" not in callers


def test_concurrent_operations_never_overlap_and_run_in_the_order_they_were_asked(host):
    log = []

    def make(n):
        def op():
            log.append(("start", n))
            time.sleep(0.05)
            log.append(("end", n))

        return op

    async def scenario():
        tasks = []
        for n in range(4):
            tasks.append(asyncio.create_task(host.run(make(n))))
            await asyncio.sleep(0.005)  # a definite order of asking
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    assert log == [event for n in range(4) for event in (("start", n), ("end", n))]


def test_an_operation_that_asks_for_another_does_not_deadlock(host):
    assert host.run_sync(lambda: host.run_sync(lambda: "inner")) == "inner"


def test_errors_reach_the_caller_and_leave_the_host_working(host):
    def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        host.run_sync(boom)

    async def async_boom():
        await host.run(boom)

    with pytest.raises(ValueError, match="bad"):
        asyncio.run(async_boom())
    assert host.run_sync(lambda: "still fine") == "still fine"


def test_giving_up_on_a_waiting_operation_does_not_break_the_ones_after_it(host):
    async def scenario():
        slow = asyncio.create_task(host.run(lambda: time.sleep(0.2)))
        waiting = asyncio.create_task(host.run(lambda: "never awaited"))
        await asyncio.sleep(0.02)
        waiting.cancel()  # e.g. the app is shutting down
        with pytest.raises(asyncio.CancelledError):
            await waiting
        await slow
        return await host.run(lambda: "next")

    assert asyncio.run(scenario()) == "next"


# --- when the browser is rebuilt -------------------------------------------------------------------------------


def test_a_browser_that_died_is_replaced_and_the_dead_one_is_cleaned_up(host, world):
    visit(host)
    world.browsers[0].connected = False  # Chromium crashed or was closed
    visit(host)
    assert host.launches == 2 and len(world.browsers) == 2
    assert world.browsers[0].closed is True and world.playwrights[0].stopped is True


def test_a_new_login_on_disk_replaces_the_browser_so_the_old_cookies_are_not_reused(host, world):
    visit(host)
    world.login_time += timedelta(minutes=5)  # `npm run auth` ran again
    visit(host)
    assert host.launches == 2
    visit(host)
    assert host.launches == 2  # and then it is stable again


def test_the_apps_own_refresh_of_the_login_file_does_not_count_as_a_new_login(host, world):
    visit(host)
    world.login_time += timedelta(minutes=5)  # we just wrote the refreshed cookies ourselves
    host.run_sync(host.login_saved)
    visit(host)
    assert host.launches == 1


def test_the_browser_is_recycled_after_the_configured_hours_so_it_cannot_leak_forever(host, world):
    visit(host)
    world.now = 11 * 3600
    visit(host)
    assert host.launches == 1
    world.now = 12 * 3600 + 1
    visit(host)
    assert host.launches == 2
    world.now += 100 * 3600
    world.recycle_hours = 0  # 0 means never
    visit(host)
    assert host.launches == 2


def test_a_moved_login_file_replaces_the_browser(host, world, tmp_path):
    visit(host)
    world.login_path = str(tmp_path / "elsewhere.json")
    visit(host)
    assert host.launches == 2
    assert world.browsers[1].contexts[0].storage_state == world.login_path


# --- failures ------------------------------------------------------------------------------------------------------


def test_with_no_saved_login_nothing_is_launched_and_the_error_says_what_to_do(host, world):
    world.has_login = False
    with pytest.raises(NeedsLoginError, match="npm run auth"):
        visit(host)
    assert world.browsers == [] and world.playwrights == []
    world.has_login = True
    assert visit(host) and host.launches == 1  # works as soon as the login exists


def test_a_failed_launch_is_a_retryable_error_and_leaves_nothing_behind(host, world):
    world.launch_error = OSError("no display")
    with pytest.raises(TransientStepError, match="browser launch failed"):
        visit(host)
    assert world.playwrights[0].stopped is True  # the half-started Playwright was stopped
    world.launch_error = None
    assert visit(host) and host.launches == 1  # the next operation simply tries again


# --- shutting down ------------------------------------------------------------------------------------------------------


def test_closing_shuts_the_browser_and_playwright_and_the_thread_down(world):
    host = world.host()
    visit(host)
    thread = host._thread
    host.close(timeout=5)
    assert world.browsers[0].closed and world.browsers[0].contexts[0].closed and world.playwrights[0].stopped
    assert not thread.is_alive()
    host.close(timeout=5)  # closing twice is harmless


def test_closing_a_host_that_never_started_does_nothing(world):
    world.host().close(timeout=1)
    assert world.browsers == []


def test_an_operation_after_close_starts_everything_again(world):
    host = world.host()
    visit(host)
    host.close(timeout=5)
    assert visit(host)
    assert host.launches == 2 and len(world.browsers) == 2  # the counter spans the host's whole life
    host.close(timeout=5)


# --- the service uses the shared browser -----------------------------------------------------------------------------------


def test_every_service_instance_shares_the_one_host():
    assert NotebookLMService().host is NotebookLMService().host is get_browser_host()


def test_submit_and_collect_run_on_the_browser_thread_one_at_a_time(world):
    host = world.host()
    service = NotebookLMService(host=host)
    log = []

    def record(name):
        def fake(*args, **kwargs):
            log.append((name, threading.current_thread().name, "start"))
            time.sleep(0.03)
            log.append((name, threading.current_thread().name, "end"))
            return {"submit": "https://notebooklm.google.com/notebook/x", "collect": ("deck.pdf", True)}[name]

        return fake

    service._sync_submit = record("submit")
    service._sync_collect = record("collect")

    async def scenario():
        return await asyncio.gather(service.submit("f", "p", "d"), service.collect("u", "d"))

    results = asyncio.run(scenario())
    host.close(timeout=5)
    assert results == ["https://notebooklm.google.com/notebook/x", ("deck.pdf", True)]
    assert {thread for _, thread, _ in log} == {"notebooklm-browser"}
    assert [state for _, _, state in log] == ["start", "end"] * 2  # never two at once


def test_the_app_closes_the_shared_browser_when_it_shuts_down(monkeypatch):
    import app.main as main_module
    from fastapi.testclient import TestClient

    closed = []

    class SpyHost:
        def close(self, timeout=15):
            closed.append(True)

    monkeypatch.setattr(main_module, "get_browser_host", lambda: SpyHost())
    with TestClient(main_module.app):
        assert closed == []
    assert closed == [True]


# --- a real browser: the session stays warm between operations ------------------------------------------------------------------


def real_host(tmp_path):
    login = tmp_path / "storage_state.json"
    login.write_text(
        json.dumps({"cookies": [{"name": "warm", "value": "from-the-login-file", "domain": "127.0.0.1", "path": "/", "expires": -1}], "origins": []}),
        encoding="utf-8",
    )
    stamp = {"time": datetime.fromtimestamp(login.stat().st_mtime, tz=timezone.utc)}
    host = BrowserHost(
        storage_path=lambda: str(login),
        login_modified_at=lambda: stamp["time"],
        headless=lambda: True,
        recycle_hours=lambda: 0,
    )
    return host, login, stamp


def test_with_a_real_chromium_the_second_operation_finds_the_session_the_first_one_built(tmp_path):
    host, login, stamp = real_host(tmp_path)
    try:
        def first():
            with host.page() as page:
                page.set_content("<h1>one</h1>")
                host.context.add_cookies([{"name": "built-by-op-1", "value": "yes", "domain": "127.0.0.1", "path": "/"}])
                return id(host.context), host._browser

        def second():
            with host.page() as page:
                names = {cookie["name"]: cookie["value"] for cookie in host.context.cookies()}
                return id(host.context), names, len(host.context.pages)

        context_one, browser = host.run_sync(first)
        context_two, cookies, open_tabs = host.run_sync(second)

        assert context_one == context_two and host.launches == 1  # one browser, one context
        assert cookies["warm"] == "from-the-login-file"  # the saved login was loaded once
        assert cookies["built-by-op-1"] == "yes"  # and what the first operation did is still there
        assert open_tabs == 1  # the first operation's tab was closed; only this one is open
    finally:
        host.close(timeout=15)
    assert browser.is_connected() is False  # closing the host closed the real browser


def test_with_a_real_chromium_a_new_login_file_is_picked_up(tmp_path):
    host, login, stamp = real_host(tmp_path)
    try:
        def read_cookie():
            with host.page():
                return {c["name"]: c["value"] for c in host.context.cookies()}.get("warm")

        assert host.run_sync(read_cookie) == "from-the-login-file"
        login.write_text(
            json.dumps({"cookies": [{"name": "warm", "value": "after-npm-run-auth", "domain": "127.0.0.1", "path": "/", "expires": -1}], "origins": []}),
            encoding="utf-8",
        )
        stamp["time"] += timedelta(minutes=1)  # the file is newer
        assert host.run_sync(read_cookie) == "after-npm-run-auth"
        assert host.launches == 2
    finally:
        host.close(timeout=15)
