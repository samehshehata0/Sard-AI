import asyncio
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from app.automation.errors import (
    NeedsLoginError,
    NotebookLMGenerationError,
    PermanentStepError,
    TransientStepError,
)
from app.automation.evidence import capture_evidence
from app.automation.locators import LocatorNotFoundError
from app.automation.pacing import HumanPacer
from app.automation.notebooklm_ui import (
    ADD_SOURCES_BUTTON,
    ARTIFACT_DOWNLOAD_PDF,
    CONFIRM_DELETE_BUTTON,
    DELETE_MENU_ITEM,
    ARTIFACT_ITEM,
    ARTIFACT_MORE_BUTTON,
    ARTIFACT_OPEN_CARD,
    COPIED_TEXT_OPTION,
    CUSTOMIZE_BUTTON,
    DISMISS_KNOWN,
    DISMISS_ONBOARDING,
    DOWNLOAD_CONTROL,
    DOWNLOAD_MENU_ITEM,
    FILE_INPUT,
    GENERATING_INDICATOR,
    HAMBURGER_BUTTON,
    HAMBURGER_MENU_ITEM,
    HAMBURGER_OWNER_BUTTON,
    INSERT_SOURCE_BUTTON,
    MODAL,
    NEW_NOTEBOOK_BUTTON,
    NOTEBOOK_CARD,
    NOTEBOOK_CARD_MENU,
    NOTEBOOK_EDITOR,
    OVERFLOW_MENU_BUTTON,
    PASTE_TEXT_AREA,
    PROMPT_FIELD,
    SLIDE_DECK_BUTTON,
    SLIDE_DECK_CARD,
    SLIDE_DECK_DIALOG,
    SOURCE_TITLE,
    WELCOME_CREATE_BUTTON,
    WELCOME_PAGE,
    build_registry,
    page_has_landed,
)
from app.automation.slide_deck import click_generate_now
from app.automation.steps import check_session, run_step, wait_until, wait_until_stable
from app.core.config import settings


logger = logging.getLogger(__name__)


def storage_state_candidates() -> list[str]:
    return [
        os.path.abspath(path)
        for path in (
            settings.NOTEBOOKLM_STORAGE_STATE_PATH,
            os.path.join(os.path.dirname(__file__), "..", "..", "storage_state.json"),
            os.path.join(os.getcwd(), "backend", "storage_state.json"),
            os.path.join(os.getcwd(), "storage_state.json"),
        )
    ]


def session_file_modified_at() -> Optional[datetime]:
    """When the saved NotebookLM login was last written (`npm run auth`), or None if there is none.

    Only looks at the files; unlike `_storage_state_path` it never tries to log in.
    """
    times = [
        os.path.getmtime(path)
        for path in storage_state_candidates()
        if os.path.isfile(path) and os.path.getsize(path) > 10
    ]
    return datetime.fromtimestamp(max(times), tz=timezone.utc) if times else None


class NotebookLMService:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.registry = build_registry()
        self.pacer = HumanPacer.from_settings(settings)

    def _storage_state_path(self) -> Optional[str]:
        for path in storage_state_candidates():
            if os.path.isfile(path) and os.path.getsize(path) > 10:
                return path

        return None

    def _handle_dialogs(self, page: Page) -> None:
        for _, locator in self.registry.candidates(page, DISMISS_KNOWN):
            try:
                if locator.count() and locator.is_visible(timeout=400):
                    self.pacer.click(page, locator)
                    wait_until(page, lambda: not locator.is_visible(), timeout_ms=1500, interval_ms=100)
            except Exception:
                continue

    def _wait_for_reaction(self, page: Page, before_url: str, before_modal: bool, before_welcome: bool) -> None:
        """After a click, wait until the page visibly reacts (or briefly give up)."""
        wait_until(
            page,
            lambda: page.url != before_url
            or self._has_visible_modal(page) != before_modal
            or self._on_welcome_page(page) != before_welcome,
            timeout_ms=2000,
            interval_ms=150,
        )

    def _on_welcome_page(self, page: Page) -> bool:
        try:
            return (
                self.registry.find(page, WELCOME_PAGE) is not None
                or self.registry.find(page, WELCOME_CREATE_BUTTON) is not None
            )
        except Exception:
            return False

    def _has_visible_modal(self, page: Page) -> bool:
        try:
            return self.registry.find(page, MODAL) is not None
        except Exception:
            return False

    def _page_has_notebook_editor(self, page: Page) -> bool:
        try:
            return "/notebook/" in page.url or self.registry.find(page, NOTEBOOK_EDITOR) is not None
        except Exception:
            return False

    def _click_first(self, page: Page, key: str, timeout: int = 1500, paced: bool = True) -> bool:
        for strategy, locator in self.registry.candidates(page, key):
            for attempt in range(3):
                try:
                    if not locator.count() or not locator.is_visible(timeout=timeout):
                        continue

                    before_url = page.url
                    before_modal = self._has_visible_modal(page)
                    before_welcome = self._on_welcome_page(page)

                    if paced:
                        self.pacer.click(page, locator)
                    else:
                        locator.click(force=True)
                    self._wait_for_reaction(page, before_url, before_modal, before_welcome)

                    after_url = page.url
                    after_modal = self._has_visible_modal(page)
                    after_welcome = self._on_welcome_page(page)
                    after_notebook = self._page_has_notebook_editor(page)

                    page_advanced = "/notebook/" in after_url or (after_notebook and not before_welcome)
                    welcome_released = before_welcome and not after_welcome

                    if page_advanced or (welcome_released and after_notebook):
                        logger.info("[Sard] NotebookLM clicked '%s' and the page really advanced: %s", key, strategy.name)
                        return True

                    if before_welcome and after_welcome:
                        logger.warning(
                            "[Sard] Click on '%s' (%s) did not leave the welcome page; retrying (%s/3)",
                            key,
                            strategy.name,
                            attempt + 1,
                        )
                        continue

                    if before_modal and after_modal and before_url == after_url:
                        logger.warning(
                            "[Sard] Click on '%s' (%s) was swallowed by a modal; retrying (%s/3)",
                            key,
                            strategy.name,
                            attempt + 1,
                        )
                        continue

                    logger.info("[Sard] NotebookLM clicked '%s': %s", key, strategy.name)
                    return True
                except Exception:
                    continue
        return False

    def _create_notebook(self, page: Page) -> None:
        created = self._click_first(page, NEW_NOTEBOOK_BUTTON, timeout=2500)
        if not created:
            page.goto(
                "https://notebooklm.google.com/notebook/new",
                wait_until="domcontentloaded",
                timeout=45000,
            )
        wait_until(page, lambda: self._page_has_notebook_editor(page), timeout_ms=15_000)
        self.pacer.pause(page)
        self._handle_dialogs(page)

    def _dismiss_onboarding_dialogs(self, page: Page) -> None:
        """
        Dismiss NotebookLM onboarding popups and welcome dialogs that may appear
        on first use or after login. These popups can block the UI and must be
        dismissed before proceeding with source upload.
        """
        for attempt in range(8):
            modal = self.registry.find(page, MODAL)
            if modal is None:
                return

            before_url = page.url
            before_welcome = self._on_welcome_page(page)
            clicked = False
            for strategy, locator in self.registry.candidates(modal.locator, DISMISS_ONBOARDING):
                try:
                    if locator.count() and locator.is_visible(timeout=500):
                        self.pacer.click(page, locator)
                        logger.info("[Sard] Dismissed NotebookLM onboarding dialog via: %s", strategy.name)
                        clicked = True
                        wait_until(page, lambda: self.registry.find(page, MODAL) is None, timeout_ms=2000, interval_ms=150)
                        break
                except Exception:
                    continue

            if not clicked:
                try:
                    page.keyboard.press("Escape")
                    wait_until(page, lambda: self.registry.find(page, MODAL) is None, timeout_ms=2000, interval_ms=150)
                except Exception:
                    pass

            modal_still_visible = self.registry.find(page, MODAL) is not None
            after_welcome = self._on_welcome_page(page)
            after_notebook = self._page_has_notebook_editor(page)

            if not modal_still_visible:
                if after_welcome and not after_notebook:
                    logger.warning(
                        "[Sard] Modal closed but NotebookLM remained on the welcome screen; retrying (%s/8)",
                        attempt + 1,
                    )
                    continue
                return

            if page.url == before_url and before_welcome and after_welcome:
                logger.warning(
                    "[Sard] NotebookLM welcome screen still active after modal dismissal; retrying (%s/8)",
                    attempt + 1,
                )
                continue

            self._handle_dialogs(page)

        logger.warning("[Sard] NotebookLM onboarding modal did not clear after repeated dismiss attempts")

    def _upload_source(self, page: Page, source_path: str, story_text: str) -> None:
        self._dismiss_onboarding_dialogs(page)
        if self._has_visible_modal(page):
            logger.warning("[Sard] NotebookLM modal still active after dismiss attempt; retrying dismissal before upload")
            self._dismiss_onboarding_dialogs(page)

        if self.registry.find(page, COPIED_TEXT_OPTION) is None:
            self._click_first(page, ADD_SOURCES_BUTTON)
            wait_until(page, lambda: self.registry.find(page, COPIED_TEXT_OPTION) is not None, timeout_ms=5000)

        for _, option in self.registry.candidates(page, COPIED_TEXT_OPTION):
            try:
                if not option.count() or not option.is_visible(timeout=1200):
                    continue
                self.pacer.click(page, option)
                text_area = self.registry.resolve(page, PASTE_TEXT_AREA, timeout_ms=5000).locator
                self.pacer.pause(page)
                # A person pastes the source in one go, so it is filled at once.
                text_area.fill(story_text)
                insert_button = self.registry.resolve(page, INSERT_SOURCE_BUTTON, timeout_ms=5000).locator
                if not wait_until(page, insert_button.is_enabled, timeout_ms=5000, interval_ms=250):
                    raise TransientStepError("Copied-text insert button was unavailable")
                self.pacer.click(page, insert_button, force=False)
                logger.info("[Sard] NotebookLM source uploaded as copied text")
                return
            except Exception:
                continue

        try:
            # The file input is usually hidden, so it only needs to exist.
            for _, file_input in self.registry.candidates(page, FILE_INPUT):
                if file_input.count():
                    file_input.set_input_files(source_path)
                    logger.info("[Sard] NotebookLM source uploaded as file")
                    return
        except Exception as exc:
            raise TransientStepError(f"NotebookLM source upload failed: {exc}") from exc

        raise TransientStepError("NotebookLM did not accept the educational source")

    def _request_slide_deck(self, page: Page, prompt: str) -> None:
        page.keyboard.press("Escape")
        wait_until(page, lambda: not self._has_visible_modal(page), timeout_ms=3000, interval_ms=150)
        self._wait_until_ready_to_generate(page)

        try:
            slide_control = self.registry.resolve(page, SLIDE_DECK_BUTTON, timeout_ms=10_000)
        except LocatorNotFoundError as exc:
            raise TransientStepError("NotebookLM Slide Deck control was not found") from exc

        self.pacer.pause(page)

        customized = False
        try:
            card = self.registry.find(slide_control.locator, SLIDE_DECK_CARD)
            customize = self.registry.find(card.locator, CUSTOMIZE_BUTTON) if card else None
            if customize is not None:
                self.pacer.click(page, customize.locator)
                customized = True
        except Exception:
            customized = False

        if not customized:
            self.pacer.click(page, slide_control.locator)

        try:
            dialog = self.registry.resolve(page, SLIDE_DECK_DIALOG, timeout_ms=5000).locator
            dialog_open = True
        except LocatorNotFoundError:
            dialog_open = False

        if dialog_open:
            prompt_field = self.registry.find(dialog, PROMPT_FIELD)
            if prompt_field is None:
                raise TransientStepError("Slide Deck dialog has no prompt field")
            self.pacer.type_text(page, prompt_field.locator, prompt)
            click_generate_now(page, self.registry, pacer=self.pacer)
        else:
            # NotebookLM accepted the click without an inline dialog; still
            # require proof that generation started.
            try:
                self.registry.resolve(page, GENERATING_INDICATOR, timeout_ms=60_000)
            except LocatorNotFoundError as exc:
                raise TransientStepError(str(exc)) from exc
            logger.info("[Sard] NotebookLM slide-deck generation started without an inline dialog")

    def _wait_until_ready_to_generate(self, page: Page) -> None:
        """Wait until the Slide Deck control has stayed enabled for a few seconds.

        This replaces a blind pause after indexing. If NotebookLM never settles
        we carry on, as before; the Generate now check still catches a real failure.
        """

        def control_ready() -> bool:
            control = self.registry.find(page, SLIDE_DECK_BUTTON)
            if control is None:
                return False
            return control.locator.is_enabled() and control.locator.get_attribute("aria-disabled") != "true"

        ready = wait_until_stable(
            page,
            control_ready,
            stable_ms=int(settings.NOTEBOOKLM_READY_STABLE_SECONDS * 1000),
            timeout_ms=60_000,
            interval_ms=500,
        )
        if not ready:
            logger.warning("[Sard] NotebookLM Slide Deck control did not settle within 60s; continuing")

    def _wait_for_source_indexing(self, page: Page, story_text: str) -> None:
        title = next(
            (line.lstrip("# ").strip() for line in story_text.splitlines() if line.strip()),
            "",
        )
        if title:
            self.registry.resolve(
                page,
                SOURCE_TITLE,
                timeout_ms=90_000,
                params={"text": json.dumps(title, ensure_ascii=False)},
            )
        self.registry.resolve(page, SLIDE_DECK_BUTTON, timeout_ms=90_000)
        logger.info("[Sard] NotebookLM source indexing completed")

    def _save_download(self, page: Page, control, target_dir: str) -> Optional[str]:
        try:
            with page.expect_download(timeout=12000) as download_info:
                control.click(force=True)
            download = download_info.value
            suffix = Path(download.suggested_filename).suffix.lower()
            if suffix not in {".pdf", ".pptx"}:
                suffix = ".pdf"
            output_path = os.path.join(target_dir, f"notebooklm_presentation{suffix}")
            download.save_as(output_path)
            if os.path.getsize(output_path) < 10_000:
                raise TransientStepError("Downloaded NotebookLM artifact is too small")
            return output_path
        except Exception:
            return None

    def _download_artifact(self, page: Page, target_dir: str) -> str:
        started_at = time.monotonic()
        deadline = started_at + settings.NOTEBOOKLM_TIMEOUT_SECONDS
        next_progress_log = 60.0
        poll_ms = max(1000, int(settings.NOTEBOOKLM_POLL_INTERVAL_SECONDS * 1000))
        while time.monotonic() < deadline:
            self._handle_dialogs(page)

            # The screenshot shows the real menu is the left-side source-item
            # hamburger (button.source-item-more-button), not the right-side artifact menu.
            download_path = self._click_all_hamburger_menus_until_download(page, target_dir)
            if download_path:
                return download_path

            # Current NotebookLM Arabic UI exposes completed slide decks as
            # artifact-library-item cards with PDF/PPTX downloads in a local menu.
            artifact = self.registry.find(page, ARTIFACT_ITEM)
            if artifact is not None:
                try:
                    more = self.registry.find(artifact.locator, ARTIFACT_MORE_BUTTON)
                    if more is not None:
                        more.locator.click(force=True)
                        wait_until(
                            page,
                            lambda: self.registry.find(page, ARTIFACT_DOWNLOAD_PDF) is not None,
                            timeout_ms=2000,
                            interval_ms=100,
                        )
                        pdf_download = self.registry.find(page, ARTIFACT_DOWNLOAD_PDF)
                        if pdf_download is not None:
                            path = self._save_download(page, pdf_download.locator, target_dir)
                            if path:
                                return path
                        page.keyboard.press("Escape")
                except Exception:
                    page.keyboard.press("Escape")

            # Open the finished artifact card/viewer if it is ready.
            self._click_first(page, ARTIFACT_OPEN_CARD, timeout=500, paced=False)

            for _, control in self.registry.candidates(page, DOWNLOAD_CONTROL):
                try:
                    if control.count() and control.is_visible(timeout=500):
                        path = self._save_download(page, control, target_dir)
                        if path:
                            return path
                except Exception:
                    continue

            # Some NotebookLM builds place Download in an overflow menu.
            if self._click_first(page, OVERFLOW_MENU_BUTTON, timeout=400):
                for _, item in self.registry.candidates(page, DOWNLOAD_MENU_ITEM):
                    try:
                        if item.count() and item.is_visible(timeout=500):
                            path = self._save_download(page, item, target_dir)
                            if path:
                                return path
                    except Exception:
                        continue
                page.keyboard.press("Escape")

            elapsed = time.monotonic() - started_at
            if elapsed >= next_progress_log:
                try:
                    generating = self.registry.find(page, GENERATING_INDICATOR) is not None
                except Exception:
                    # NotebookLM can briefly replace the page while an artifact
                    # card is materializing. A status log must never terminate
                    # an otherwise healthy generation poll.
                    generating = False
                logger.info(
                    "[Sard] NotebookLM slide deck still pending: elapsed=%.0fs state=%s timeout=%ss",
                    elapsed,
                    "generating" if generating else "waiting-for-artifact",
                    settings.NOTEBOOKLM_TIMEOUT_SECONDS,
                )
                next_progress_log += 60.0
            page.wait_for_timeout(poll_ms)

        raise TransientStepError(
            f"NotebookLM slide deck did not finish within {settings.NOTEBOOKLM_TIMEOUT_SECONDS} seconds"
        )

    def _click_all_hamburger_menus_until_download(self, page: Page, target_dir: str) -> Optional[str]:
        """Click every visible NotebookLM hamburger/menu button until the PDF/PPTX
        download action appears. This intentionally includes the left-side source
        item menu shown in the screenshot, because that is the real menu that can
        expose the artifact download action in the current NotebookLM UI."""
        for _, locators in self.registry.all_matches(page, HAMBURGER_BUTTON):
            try:
                count = locators.count()
                for i in range(count):
                    button = locators.nth(i)
                    try:
                        if not button.is_visible(timeout=200):
                            continue
                    except Exception:
                        continue

                    try:
                        if button.get_attribute("data-sard-clicked") == "1":
                            continue
                    except Exception:
                        pass

                    try:
                        button.click(force=True)
                        button.evaluate("el => el.setAttribute('data-sard-clicked', '1')")
                    except Exception:
                        try:
                            owner = self.registry.find(button, HAMBURGER_OWNER_BUTTON)
                            if owner is None:
                                continue
                            owner.locator.click(force=True)
                        except Exception:
                            continue

                    wait_until(
                        page,
                        lambda: self.registry.find(page, HAMBURGER_MENU_ITEM) is not None,
                        timeout_ms=1500,
                        interval_ms=100,
                    )
                    download_item = self.registry.find(page, HAMBURGER_MENU_ITEM)
                    if download_item is not None:
                        return self._save_download(page, download_item.locator, target_dir)

                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
            except Exception:
                continue

        return None

    @contextmanager
    def _session(self, start_url: str, target_dir: str):
        """One browser session on NotebookLM, with the login applied and evidence saved on failure.

        Yields (page, step). The browser is always closed on the way out.
        """
        os.makedirs(target_dir, exist_ok=True)
        storage_path = self._storage_state_path()
        if not storage_path:
            raise NeedsLoginError("NotebookLM authentication is missing; run the repository auth command")

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS,
                    ignore_default_args=["--enable-automation"],
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
            except Exception as exc:
                raise TransientStepError(f"Playwright browser launch failed: {exc}") from exc

            try:
                context = browser.new_context(
                    storage_state=storage_path,
                    viewport={"width": 1440, "height": 900},
                )
                page = context.new_page()
                page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
                wait_until(page, lambda: page_has_landed(page, self.registry), timeout_ms=15_000)

                evidence_dir = os.path.join(target_dir, "notebooklm_artifacts")
                quota_markers = settings.NOTEBOOKLM_QUOTA_MARKERS

                def step(name, action, **conditions):
                    return run_step(
                        page,
                        name,
                        action,
                        evidence_dir=evidence_dir,
                        quota_markers=quota_markers,
                        **conditions,
                    )

                try:
                    check_session(page, quota_markers)
                    yield page, step
                except Exception as exc:
                    if getattr(exc, "evidence_dir", None) is None:
                        evidence = capture_evidence(page, evidence_dir, "pipeline", exc)
                        if isinstance(exc, NotebookLMGenerationError):
                            exc.evidence_dir = evidence
                        logger.error("[Sard] NotebookLM evidence saved to: %s", evidence)
                    raise
            finally:
                browser.close()

    def _sync_submit(
        self,
        file_path: str,
        prompt: str,
        target_dir: str,
        notebook_url: Optional[str] = None,
        on_notebook: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Create a notebook, add the source and ask for the Slide Deck. Returns the notebook's URL.

        `on_notebook` is called with the URL the moment the notebook exists, so it can be saved
        before anything else can go wrong. Given a `notebook_url` from an earlier try, the work
        continues in that notebook instead of creating another.
        """
        story_text = Path(file_path).read_text(encoding="utf-8").strip()
        if not story_text:
            raise PermanentStepError("The educational source is empty")

        logger.info("[Sard] NotebookLM submit started (resuming=%s)", bool(notebook_url))
        with self._session(notebook_url or settings.NOTEBOOKLM_URL, target_dir) as (page, step):
            if notebook_url:
                if (
                    self.registry.find(page, GENERATING_INDICATOR) is not None
                    or self.registry.find(page, ARTIFACT_ITEM) is not None
                ):
                    logger.info("[Sard] The Slide Deck was already requested in %s", notebook_url)
                    return page.url
                title = next((line.lstrip("# ").strip() for line in story_text.splitlines() if line.strip()), "")
                source_added = bool(title) and self.registry.find(
                    page, SOURCE_TITLE, params={"text": json.dumps(title, ensure_ascii=False)}
                ) is not None
                if source_added:
                    step("await_source", lambda: self._wait_for_source_indexing(page, story_text))
                else:
                    step(
                        "add_source",
                        lambda: self._upload_source(page, file_path, story_text),
                        pre=lambda: self._page_has_notebook_editor(page),
                        post=lambda: self._wait_for_source_indexing(page, story_text),
                    )
            else:
                step(
                    "create_notebook",
                    lambda: (self._create_notebook(page), self._dismiss_onboarding_dialogs(page)),
                    post=lambda: wait_until(page, lambda: self._page_has_notebook_editor(page)),
                )
                if on_notebook is not None:
                    on_notebook(page.url)
                step(
                    "add_source",
                    lambda: self._upload_source(page, file_path, story_text),
                    pre=lambda: self._page_has_notebook_editor(page),
                    post=lambda: self._wait_for_source_indexing(page, story_text),
                )
            step("request_slide_deck", lambda: self._request_slide_deck(page, prompt))
            logger.info("[Sard] NotebookLM Slide Deck requested in %s", page.url)
            return page.url

    def _sync_collect(self, notebook_url: str, target_dir: str) -> tuple[str, bool]:
        """Wait for the Slide Deck in an existing notebook and download it.

        Returns (path, notebook_deleted). Once the download is verified the notebook is deleted
        so a free account does not fill up; if that fails it is logged and the download still counts.
        """
        logger.info("[Sard] NotebookLM collect started: %s", notebook_url)
        with self._session(notebook_url, target_dir) as (page, step):
            artifact_path = step("collect", lambda: self._download_artifact(page, target_dir))
            logger.info("[Sard] NotebookLM artifact downloaded: %s", artifact_path)
            return artifact_path, self._delete_notebook(page, notebook_url)

    def _delete_notebook(self, page: Page, notebook_url: str) -> bool:
        """Delete a notebook from the home page. Never raises: a failure is logged and reported as False."""
        try:
            notebook_id = notebook_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            params = {"id": notebook_id}
            page.goto(settings.NOTEBOOKLM_URL, wait_until="domcontentloaded", timeout=45000)
            wait_until(page, lambda: page_has_landed(page, self.registry), timeout_ms=15_000)

            timeout = settings.NOTEBOOKLM_DELETE_TIMEOUT_MS
            card = self.registry.resolve(page, NOTEBOOK_CARD, timeout_ms=timeout, params=params)
            menu = self.registry.resolve(page, NOTEBOOK_CARD_MENU, timeout_ms=timeout, scope=card.locator)
            self.pacer.click(page, menu.locator)
            delete = self.registry.resolve(page, DELETE_MENU_ITEM, timeout_ms=timeout)
            self.pacer.click(page, delete.locator)
            confirm = self.registry.resolve(page, CONFIRM_DELETE_BUTTON, timeout_ms=timeout)
            self.pacer.click(page, confirm.locator)

            gone = wait_until(
                page,
                lambda: self.registry.find(page, NOTEBOOK_CARD, params=params) is None,
                timeout_ms=timeout,
            )
            if gone:
                logger.info("[Sard] Deleted NotebookLM notebook %s", notebook_id)
            else:
                logger.warning("[Sard] NotebookLM notebook %s still listed after deleting it", notebook_id)
            return gone
        except Exception as exc:
            logger.warning("[Sard] Could not delete NotebookLM notebook %s: %s", notebook_url, exc)
            return False

    async def submit(
        self,
        file_path: str,
        prompt: str,
        target_dir: str,
        notebook_url: Optional[str] = None,
        on_notebook: Optional[Callable[[str], None]] = None,
    ) -> str:
        return await asyncio.to_thread(self._sync_submit, file_path, prompt, target_dir, notebook_url, on_notebook)

    async def collect(self, notebook_url: str, target_dir: str) -> tuple[str, bool]:
        return await asyncio.to_thread(self._sync_collect, notebook_url, target_dir)
