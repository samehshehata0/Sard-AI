"""One long-lived NotebookLM browser, shared by every job.

Instead of starting a Chromium for each Submit and Collect, the app keeps a single browser open and
signed in, and each operation opens a fresh tab in it. The session stays warm (cookies rotate in place,
no new-device sign-in each time), and there is one place that knows about the browser.

Playwright's synchronous API belongs to the thread that started it, so the browser lives on one
dedicated thread and every operation is queued onto it. That also makes browser work serial: with one
Google account NotebookLM generates one deck at a time, so nothing is lost.

The browser is rebuilt when it has to be:
- it died or was closed;
- the saved login changed on disk (`npm run auth` was run again), so the old cookies are not reused;
- it has been open for `recycle_hours`, so a long-running Chromium does not slowly leak memory.
Saving the refreshed login ourselves is not a change: `login_saved()` records it.
"""
import asyncio
import logging
import queue
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from app.automation.errors import NeedsLoginError, TransientStepError


logger = logging.getLogger(__name__)

T = TypeVar("T")
_STOP = object()


def _start_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright().start()


class BrowserHost:
    def __init__(
        self,
        storage_path: Callable[[], Optional[str]],
        login_modified_at: Callable[[], Optional[datetime]],
        headless: Callable[[], bool] = lambda: True,
        recycle_hours: Callable[[], float] = lambda: 12.0,
        start_playwright: Callable[[], Any] = _start_playwright,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._storage_path_fn = storage_path
        self._login_modified_at = login_modified_at
        self._headless = headless
        self._recycle_hours = recycle_hours
        self._start_playwright = start_playwright
        self._clock = clock

        self._jobs: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()

        # Only touched on the browser thread.
        self._playwright = None
        self._browser = None
        self._context = None
        self._storage_path: Optional[str] = None
        self._loaded_login_time: Optional[datetime] = None
        self._launched_at = 0.0
        self.launches = 0

    # --- the browser thread -----------------------------------------------------------------------

    def _ensure_thread(self) -> None:
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._serve, name="notebooklm-browser", daemon=True)
                self._thread.start()

    def _serve(self) -> None:
        while True:
            item = self._jobs.get()
            if item is _STOP:
                self._teardown()
                return
            fn, done = item
            try:
                result = fn()
            except BaseException as exc:  # handed back to whoever asked, never lost on this thread
                done(None, exc)
            else:
                done(result, None)

    def run_sync(self, fn: Callable[[], T]) -> T:
        """Run `fn` on the browser thread and wait for it. Safe to call from the browser thread itself."""
        if threading.current_thread() is self._thread:
            return fn()
        self._ensure_thread()
        finished = threading.Event()
        box: dict[str, Any] = {}

        def done(result, error):
            box["result"], box["error"] = result, error
            finished.set()

        self._jobs.put((fn, done))
        finished.wait()
        if box["error"] is not None:
            raise box["error"]
        return box["result"]

    async def run(self, fn: Callable[[], T]) -> T:
        """Run `fn` on the browser thread without blocking the event loop. Operations run one at a time, in order."""
        if threading.current_thread() is self._thread:
            return fn()
        self._ensure_thread()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        def settle(result, error):
            def apply():
                if future.cancelled():
                    return
                if error is not None:
                    future.set_exception(error)
                else:
                    future.set_result(result)

            loop.call_soon_threadsafe(apply)

        self._jobs.put((fn, settle))
        return await future

    # --- the browser (call these only from inside `run`) -----------------------------------------------

    def _teardown(self) -> None:
        for thing, closer in ((self._context, "close"), (self._browser, "close"), (self._playwright, "stop")):
            if thing is not None:
                try:
                    getattr(thing, closer)()
                except Exception as exc:
                    logger.debug("[Sard] Closing the NotebookLM browser: %s", exc)
        self._playwright = self._browser = self._context = None
        self._storage_path = None

    def _is_usable(self, path: str) -> bool:
        if self._context is None or path != self._storage_path:
            return False
        try:
            if not self._browser.is_connected():
                logger.warning("[Sard] The NotebookLM browser is gone; starting a new one")
                return False
        except Exception:
            return False
        saved = self._login_modified_at()
        if saved is not None and (self._loaded_login_time is None or saved > self._loaded_login_time):
            logger.info("[Sard] The saved login changed on disk; starting the browser again with it")
            return False
        recycle = self._recycle_hours()
        if recycle > 0 and self._clock() - self._launched_at > recycle * 3600:
            logger.info("[Sard] The NotebookLM browser has been open for %.0f hours; recycling it", recycle)
            return False
        return True

    def _ensure(self):
        path = self._storage_path_fn()
        if not path:
            raise NeedsLoginError("NotebookLM authentication is missing; run `npm run auth`")
        if self._is_usable(path):
            return self._context

        self._teardown()
        try:
            self._playwright = self._start_playwright()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless(),
                ignore_default_args=["--enable-automation"],
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            self._context = self._browser.new_context(storage_state=path, viewport={"width": 1440, "height": 900})
        except Exception as exc:
            self._teardown()
            raise TransientStepError(f"Playwright browser launch failed: {exc}") from exc
        self._storage_path = path
        self._loaded_login_time = self._login_modified_at()
        self._launched_at = self._clock()
        self.launches += 1
        logger.info("[Sard] Started the NotebookLM browser (launch #%s)", self.launches)
        return self._context

    @property
    def context(self):
        return self._context

    @property
    def storage_path(self) -> Optional[str]:
        return self._storage_path

    def login_saved(self) -> None:
        """We just wrote the login file ourselves: that is not a new sign-in, so do not rebuild the browser."""
        self._loaded_login_time = self._login_modified_at()

    @contextmanager
    def page(self):
        """A fresh tab in the shared browser, closed again afterwards."""
        context = self._ensure()
        page = context.new_page()
        try:
            yield page
        finally:
            try:
                page.close()
            except Exception:
                pass

    def close(self, timeout: float = 15) -> None:
        """Close the browser (at shutdown). If it is busy with a long operation, give up waiting after `timeout`."""
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        self._jobs.put(_STOP)
        thread.join(timeout)
