import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from app.core.config import settings


logger = logging.getLogger(__name__)


class NotebookLMGenerationError(RuntimeError):
    user_message = "تعذر إنشاء العرض التعليمي عبر NotebookLM. يرجى إعادة المحاولة."


class NotebookLMService:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def _storage_state_path(self) -> Optional[str]:
        possible_paths = [
            settings.NOTEBOOKLM_STORAGE_STATE_PATH,
            os.path.join(os.path.dirname(__file__), "..", "..", "storage_state.json"),
            os.path.join(os.getcwd(), "backend", "storage_state.json"),
            os.path.join(os.getcwd(), "storage_state.json"),
        ]
        for candidate in possible_paths:
            path = os.path.abspath(candidate)
            if os.path.isfile(path) and os.path.getsize(path) > 10:
                return path

        try:
            from save_auth import ensure_notebooklm_session

            generated_path = ensure_notebooklm_session()
            if generated_path and os.path.isfile(generated_path) and os.path.getsize(generated_path) > 10:
                return generated_path
        except Exception as exc:
            logger.warning("[Sard] NotebookLM auto-authentication failed: %s", exc)

        return None

    def _job_state_path(self, target_dir: str) -> str:
        return os.path.join(target_dir, "notebooklm_job.json")

    def _save_job_state(self, target_dir: str, notebook_url: str) -> None:
        state = {
            "notebook_url": notebook_url,
            "created_at_epoch": time.time(),
        }
        Path(self._job_state_path(target_dir)).write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )

    def _resumable_notebook_url(self, target_dir: str) -> Optional[str]:
        state_path = self._job_state_path(target_dir)
        if not os.path.isfile(state_path):
            return None
        try:
            state = json.loads(Path(state_path).read_text(encoding="utf-8"))
            notebook_url = str(state.get("notebook_url", ""))
            created_at = float(state.get("created_at_epoch", 0))
            age = time.time() - created_at
            if (
                "/notebook/" in notebook_url
                and 0 <= age <= settings.NOTEBOOKLM_RESUME_MAX_AGE_SECONDS
            ):
                return notebook_url
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("[Sard] Could not read NotebookLM resume state: %s", exc)
        return None

    def _handle_dialogs(self, page: Page) -> None:
        for selector in (
            "[role='dialog'] button:has-text('Got it')",
            "[role='dialog'] button:has-text('Dismiss')",
            "[role='dialog'] button:has-text('Accept all')",
            "[role='dialog'] button:has-text('موافق')",
            "[role='dialog'] button:has-text('فهمت')",
            "[role='dialog'] button:has-text('حسنًا')",
            "[role='dialog'] button:has-text('لنبدأ')",
            "[role='dialog'] button:has-text('ابدأ')",
            "[role='dialog'] button:has-text('Get started')",
            "[role='dialog'] button:has-text('Let\'s get started')",
            "[role='dialog'] button:has-text('تجاهل')",
            "[role='dialog'] button:has-text('OK')",
            "[role='alertdialog'] button:has-text('OK')",
            "[role='alertdialog'] button:has-text('حسنًا')",
            "[role='alertdialog'] button:has-text('لنبدأ')",
            "[role='alertdialog'] button:has-text('ابدأ')",
            "[role='alertdialog'] button:has-text('Get started')",
        ):
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=400):
                    locator.click(force=True)
                    page.wait_for_timeout(500)
            except Exception:
                continue

    def _on_welcome_page(self, page: Page) -> bool:
        try:
            welcome = page.locator("welcome-page, .welcome-page-container").first
            create_button = page.locator(
                "button.create-new-button, .create-new-button, [aria-label*='إنشاء ورقة ملاحظات جديدة']"
            ).first
            return (welcome.count() > 0 and welcome.is_visible(timeout=250)) or (
                create_button.count() > 0 and create_button.is_visible(timeout=250)
            )
        except Exception:
            return False

    def _has_visible_modal(self, page: Page) -> bool:
        try:
            modal = page.locator("[role='dialog'], [role='alertdialog'], [aria-modal='true']").first
            return modal.count() > 0 and modal.is_visible(timeout=250)
        except Exception:
            return False

    def _page_has_notebook_editor(self, page: Page) -> bool:
        try:
            notebook_url = "/notebook/" in page.url
            notebook_header = page.locator(
                ".notebook-header-container, .notebook-page, .notebook-editor, textarea, [contenteditable='true']").first
            editor_visible = notebook_header.count() > 0 and notebook_header.is_visible(timeout=300)
            return notebook_url or editor_visible
        except Exception:
            return False

    def _click_first(self, page: Page, selectors: tuple[str, ...], timeout: int = 1500) -> bool:
        for selector in selectors:
            for attempt in range(3):
                try:
                    locator = page.locator(selector).first
                    if not locator.count() or not locator.is_visible(timeout=timeout):
                        continue

                    before_url = page.url
                    before_modal = self._has_visible_modal(page)
                    before_welcome = self._on_welcome_page(page)

                    locator.click(force=True)
                    page.wait_for_timeout(600)

                    after_url = page.url
                    after_modal = self._has_visible_modal(page)
                    after_welcome = self._on_welcome_page(page)
                    after_notebook = self._page_has_notebook_editor(page)

                    page_advanced = "/notebook/" in after_url or (after_notebook and not before_welcome)
                    modal_closed = before_modal and not after_modal
                    welcome_released = before_welcome and not after_welcome

                    if page_advanced or (welcome_released and after_notebook):
                        logger.info("[Sard] NotebookLM clicked control and the page really advanced: %s", selector)
                        return True

                    if before_welcome and after_welcome:
                        logger.warning(
                            "[Sard] Click on '%s' did not leave the welcome page; retrying (%s/3)",
                            selector,
                            attempt + 1,
                        )
                        continue

                    if before_modal and after_modal and before_url == after_url:
                        logger.warning(
                            "[Sard] Click on '%s' was swallowed by a modal; retrying (%s/3)",
                            selector,
                            attempt + 1,
                        )
                        continue

                    logger.info("[Sard] NotebookLM clicked control: %s", selector)
                    return True
                except Exception:
                    continue
        return False

    def _create_notebook(self, page: Page) -> None:
        # NotebookLM's current UI uses a "new note / new notebook" card/button in Arabic
        # on the main landing page, not the older English text-only selectors.
        home_page_new_selectors = (
            "button:has-text('إنشاء دفتر ملاحظات')",
            "button:has-text('إنشاء دفتر ملاحظات جديد')",
            "button:has-text('إضافة ملاحظة جديدة')",
            "button:has-text('Add note')",
            "button:has-text('New note')",
            "button:has-text('New notebook')",
            "button:has-text('Create new note')",
            "button:has-text('Create new notebook')",
            "button:has-text('Create notebook')",
            "button:has-text('Create new')",
            "button:has-text('دفتر ملاحظات جديد')",
            "[aria-label='إنشاء دفتر ملاحظات']",
            "[aria-label='إنشاء دفتر ملاحظات جديد']",
            "[aria-label='إضافة ملاحظة جديدة']",
            "[aria-label='Create new note']",
            "[aria-label='Create new notebook']",
            "[aria-label='Create new']",
            "[aria-label='New notebook']",
            "[aria-label='New note']",
            "div:has-text('إضافة ملاحظة جديدة')",
            "div:has-text('New note')",
            "div:has-text('Create new')",
            "button.create-new-button",
        )

        created = self._click_first(page, home_page_new_selectors, timeout=2500)
        if not created:
            legacy_selectors = (
                "button:has-text('New Notebook')",
                "button:has-text('Create new')",
                "button:has-text('Create notebook')",
                "button:has-text('دفتر ملاحظات جديد')",
                "[aria-label='إنشاء ورقة ملاحظات جديدة']",
                "[aria-label='Create new notebook']",
                "[aria-label='Create new']",
            )
            created = self._click_first(page, legacy_selectors, timeout=2500)
        if not created:
            page.goto(
                "https://notebooklm.google.com/notebook/new",
                wait_until="domcontentloaded",
                timeout=45000,
            )
        page.wait_for_timeout(3500)
        self._handle_dialogs(page)

    def _dismiss_onboarding_dialogs(self, page: Page) -> None:
        """
        Dismiss NotebookLM onboarding popups and welcome dialogs that may appear
        on first use or after login. These popups can block the UI and must be
        dismissed before proceeding with source upload.
        """
        modal_selector = "[role='dialog'], [role='alertdialog'], [aria-modal='true']"
        dismiss_selectors = (
            "button:has-text('حسنًا')",
            "button:has-text('لنبدأ')",
            "button:has-text('ابدأ')",
            "button:has-text('OK')",
            "button:has-text('Get started')",
            "button:has-text('Let\'s get started')",
            "button:has-text('Got it')",
            "button:has-text('I understand')",
            "button:has-text('موافق')",
            "button:has-text('فهمت')",
            "button:has-text('Continue')",
            "button:has-text('Next')",
            "button:has-text('Dismiss')",
            "button:has-text('Close')",
            "button:has-text('تجاهل')",
            "button:has-text('إغلاق')",
        )

        for attempt in range(8):
            modal = page.locator(modal_selector).first
            if modal.count() == 0:
                return
            if not modal.is_visible(timeout=500):
                return

            before_url = page.url
            before_welcome = self._on_welcome_page(page)
            clicked = False
            for selector in dismiss_selectors:
                try:
                    locator = modal.locator(selector).first
                    if locator.count() and locator.is_visible(timeout=500):
                        locator.click(force=True)
                        logger.info("[Sard] Dismissed NotebookLM onboarding dialog via: %s", selector)
                        clicked = True
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    continue

            if not clicked:
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)
                except Exception:
                    pass

            after_modal = page.locator(modal_selector)
            modal_still_visible = after_modal.count() > 0 and after_modal.first.is_visible(timeout=400)
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
        if page.locator("[role='dialog'], [role='alertdialog'], [aria-modal='true']").count() > 0:
            logger.warning("[Sard] NotebookLM modal still active after dismiss attempt; retrying dismissal before upload")
            self._dismiss_onboarding_dialogs(page)
        copied_text_selectors = (
            "button:has-text('Copied text')",
            "button:has-text('Text')",
            "mat-card:has-text('Copied text')",
            "button:has-text('نص منسوخ')",
        )
        copied_text_visible = any(
            page.locator(selector).first.count()
            and page.locator(selector).first.is_visible(timeout=500)
            for selector in copied_text_selectors
        )
        if not copied_text_visible:
            self._click_first(
                page,
                (
                    "button:has-text('إضافة مصادر')",
                    "button:has-text('Add sources')",
                    "button[aria-label='إضافة مصدر']",
                    "button[aria-label='Add sources']",
                    "[aria-label='إضافة مصدر']",
                    "[aria-label='Add sources']",
                    "button:has-text('إضافة مصدر')",
                ),
            )
            page.wait_for_timeout(1500)

        for selector in copied_text_selectors:
            try:
                option = page.locator(selector).first
                if not option.count() or not option.is_visible(timeout=1200):
                    continue
                option.click(force=True)
                page.wait_for_timeout(1000)
                text_area = page.locator(
                    "textarea[placeholder*='الصق النص'], textarea[placeholder*='Paste text']"
                ).last
                if not text_area.count():
                    text_area = page.locator("[role='dialog'] textarea").last
                text_area.wait_for(state="visible", timeout=5000)
                text_area.fill(story_text)
                insert_button = page.locator(
                    "[role='dialog'] button:has-text('إدراج'), "
                    "[role='dialog'] button:has-text('Insert'), "
                    "[role='dialog'] button:has-text('Save')"
                ).last
                insert_button.wait_for(state="visible", timeout=5000)
                for _ in range(20):
                    if insert_button.is_enabled():
                        break
                    page.wait_for_timeout(250)
                if not insert_button.is_enabled():
                    raise NotebookLMGenerationError("Copied-text insert button was unavailable")
                insert_button.click()
                logger.info("[Sard] NotebookLM source uploaded as copied text")
                return
            except Exception:
                continue

        try:
            file_input = page.locator("input[type='file']").first
            if file_input.count():
                file_input.set_input_files(source_path)
                logger.info("[Sard] NotebookLM source uploaded as file")
                return
        except Exception as exc:
            raise NotebookLMGenerationError(f"NotebookLM source upload failed: {exc}") from exc

        raise NotebookLMGenerationError("NotebookLM did not accept the educational source")

    def _request_slide_deck(self, page: Page, prompt: str) -> None:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)

        slide_selectors = (
            "div[role='button'][aria-label='مجموعة شرائح']",
            "basic-create-artifact-button[aria-label='مجموعة الشرايح']",
            "button[aria-label=' مجموعة الشرايح']",
            "[aria-label=' مجموعة الشرايح']",
            "button:has-text('مجموعة الشرايح')",
            "button:has-text('Slide Deck')",
            "button:has-text('Slides')",
            "[role='button'][aria-label=' مجموعة الشرايح']",
            "[role='button']:has-text(' مجموعة الشرائح')",
            "button:has-text('عرض شرائح')",
            "[aria-label*='Slide Deck']",
            "[aria-label*='عرض شرائح']",
        )
        slide_control = None
        for selector in slide_selectors:
            try:
                candidate = page.locator(selector).first
                if candidate.count() and candidate.is_visible(timeout=2500):
                    slide_control = candidate
                    break
            except Exception:
                continue
        if slide_control is None:
            raise NotebookLMGenerationError("NotebookLM Slide Deck control was not found")

        page.wait_for_timeout(1500)

        customized = False
        try:
            container = slide_control.locator("xpath=ancestor::*[self::div or self::mat-card][1]")
            customize = container.locator(
                "button[aria-label*='ustom'], button[title*='ustom'], button:has-text('Customize'), button:has-text('تخصيص')"
            ).first
            if customize.count() and customize.is_visible(timeout=1500):
                customize.click(force=True)
                customized = True
        except Exception:
            customized = False

        if not customized:
            slide_control.click(force=True)

        page.wait_for_timeout(2500)

        dialog = page.locator("[role='dialog']").last
        prompt_applied = False
        try:
            if dialog.count() and dialog.is_visible(timeout=3000):
                text_area = dialog.locator("textarea, [contenteditable='true']").first
                if text_area.count() and text_area.is_visible(timeout=2000):
                    text_area.fill(prompt)
                    prompt_applied = True
                generate = dialog.locator(
                    "button:has-text('Generate'), button:has-text('Create'), button:has-text('إنشاء'), button:has-text('توليد')"
                ).first
                if generate.count() and generate.is_visible(timeout=2000):
                    generate.click(force=True)
        except Exception:
            pass

        if not prompt_applied:
            page.wait_for_timeout(4000)
            if page.locator("[role='dialog']").count() == 0:
                logger.info("[Sard] NotebookLM slide-deck generation action accepted without an inline dialog")
                return

        logger.info("[Sard] NotebookLM slide-deck generation requested")

    def _wait_for_source_indexing(self, page: Page, story_text: str) -> None:
        title = next(
            (line.lstrip("# ").strip() for line in story_text.splitlines() if line.strip()),
            "",
        )
        if title:
            page.get_by_text(title, exact=False).last.wait_for(state="visible", timeout=90000)
        page.locator(
            "div[role='button'][aria-label='مجموعة شرائح'], "
            "basic-create-artifact-button[aria-label='مجموعة الشرايح'], "
            "button[aria-label=' مجموعة الشرايح'], "
            "button:has-text('مجموعة الشرايح')"
        ).first.wait_for(state="visible", timeout=90000)
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
                raise NotebookLMGenerationError("Downloaded NotebookLM artifact is too small")
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
            artifact_items = page.locator(
                "artifact-library-item:has(button[aria-description='مجموعة الشرائح']), "
                "artifact-library-item:has(button[aria-description='Slide Deck'])"
            )
            if artifact_items.count():
                artifact = artifact_items.last
                more = artifact.locator(
                    "button[aria-label='المزيد'], button[aria-label*='More']"
                ).last
                try:
                    if more.count() and more.is_visible(timeout=500):
                        more.click(force=True)
                        page.wait_for_timeout(500)
                        pdf_download = page.locator(
                            "[role='menuitem']:has-text('تنزيل مستند PDF'), "
                            "[role='menuitem']:has-text('Download PDF')"
                        ).last
                        if pdf_download.count() and pdf_download.is_visible(timeout=1000):
                            path = self._save_download(page, pdf_download, target_dir)
                            if path:
                                return path
                        page.keyboard.press("Escape")
                except Exception:
                    page.keyboard.press("Escape")

            # Open the finished artifact card/viewer if it is ready.
            self._click_first(
                page,
                (
                    "button:has-text('Slide Deck'):not(:has-text('Generate'))",
                    "[aria-label*='Open Slide Deck']",
                    "button:has-text('عرض الشرائح')",
                ),
                timeout=500,
            )
            page.wait_for_timeout(800)

            for selector in (
                "button[aria-label*='Download']",
                "button[title*='Download']",
                "a[download]",
                "button:has-text('Download')",
                "button[aria-label*='تنزيل']",
                "button:has-text('تنزيل')",
            ):
                try:
                    control = page.locator(selector).last
                    if control.count() and control.is_visible(timeout=500):
                        path = self._save_download(page, control, target_dir)
                        if path:
                            return path
                except Exception:
                    continue

            # Some NotebookLM builds place Download in an overflow menu.
            if self._click_first(
                page,
                ("button[aria-label*='More']", "button[aria-label*='المزيد']"),
                timeout=400,
            ):
                for selector in ("[role='menuitem']:has-text('Download')", "[role='menuitem']:has-text('تنزيل')"):
                    try:
                        item = page.locator(selector).last
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
                    body_text = page.locator("body").inner_text(timeout=5000)
                except Exception:
                    # NotebookLM can briefly replace the page body while an
                    # artifact card is materializing. A status log must never
                    # terminate an otherwise healthy generation poll.
                    body_text = ""
                state = (
                    "generating"
                    if "جارٍ إنشاء مجموعة الشرائح" in body_text
                    or "Creating slide deck" in body_text
                    else "waiting-for-artifact"
                )
                logger.info(
                    "[Sard] NotebookLM slide deck still pending: elapsed=%.0fs state=%s timeout=%ss",
                    elapsed,
                    state,
                    settings.NOTEBOOKLM_TIMEOUT_SECONDS,
                )
                next_progress_log += 60.0
            page.wait_for_timeout(poll_ms)

        raise NotebookLMGenerationError(
            f"NotebookLM slide deck did not finish within {settings.NOTEBOOKLM_TIMEOUT_SECONDS} seconds"
        )

    def _save_debug_artifacts(self, page: Page, target_dir: str) -> str:
        artifact_dir = os.path.join(target_dir, "notebooklm_artifacts")
        os.makedirs(artifact_dir, exist_ok=True)

        screenshot_path = os.path.join(artifact_dir, "notebooklm_failure.png")
        html_path = os.path.join(artifact_dir, "notebooklm_page.html")
        body_html_path = os.path.join(artifact_dir, "notebooklm_body.html")

        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception as exc:
            logger.warning("[Sard] Could not capture NotebookLM screenshot: %s", exc)

        try:
            page_html = page.content()
            Path(html_path).write_text(page_html, encoding="utf-8")
        except Exception as exc:
            logger.warning("[Sard] Could not save NotebookLM page HTML: %s", exc)

        try:
            body_html = page.locator("body").evaluate("(element) => element.outerHTML")
            if body_html:
                Path(body_html_path).write_text(body_html, encoding="utf-8")
        except Exception as exc:
            logger.warning("[Sard] Could not save NotebookLM body HTML: %s", exc)

        return artifact_dir

    def _sync_pipeline(self, file_path: str, prompt: str, target_dir: str) -> str:
        os.makedirs(target_dir, exist_ok=True)
        story_text = Path(file_path).read_text(encoding="utf-8").strip()
        if not story_text:
            raise NotebookLMGenerationError("The educational source is empty")

        storage_path = self._storage_state_path()
        if not storage_path:
            raise NotebookLMGenerationError(
                "NotebookLM authentication is missing; run the repository auth command"
            )

        logger.info("[Sard] NotebookLM generation started")
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS,
                    ignore_default_args=["--enable-automation"],
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
            except Exception as exc:
                raise NotebookLMGenerationError(f"Playwright browser launch failed: {exc}") from exc

            try:
                context = browser.new_context(
                    storage_state=storage_path,
                    viewport={"width": 1440, "height": 900},
                )
                page = context.new_page()
                resume_url = self._resumable_notebook_url(target_dir)
                page.goto(
                    resume_url or settings.NOTEBOOKLM_URL,
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                page.wait_for_timeout(4000)
                if "accounts.google.com" in page.url or "signin" in page.url:
                    raise NotebookLMGenerationError("NotebookLM authentication session expired")

                try:
                    if resume_url:
                        logger.info("[Sard] Resuming pending NotebookLM slide deck: %s", resume_url)
                        artifact_path = self._download_artifact(page, target_dir)
                        logger.info("[Sard] Resumed NotebookLM artifact downloaded: %s", artifact_path)
                        return artifact_path

                    self._create_notebook(page)
                    self._dismiss_onboarding_dialogs(page)
                    self._upload_source(page, file_path, story_text)
                    logger.info("[Sard] Waiting for NotebookLM source indexing")
                    self._wait_for_source_indexing(page, story_text)
                    page.wait_for_timeout(15000)
                    self._request_slide_deck(page, prompt)
                    self._save_job_state(target_dir, page.url)
                    artifact_path = self._download_artifact(page, target_dir)
                    logger.info("[Sard] NotebookLM artifact downloaded: %s", artifact_path)
                    return artifact_path
                except Exception:
                    debug_dir = self._save_debug_artifacts(page, target_dir)
                    logger.error("[Sard] NotebookLM debug artifacts saved to: %s", debug_dir)
                    raise
            finally:
                browser.close()

    async def run_pipeline(self, file_path: str, prompt: str, target_dir: str) -> str:
        return await asyncio.to_thread(self._sync_pipeline, file_path, prompt, target_dir)

    def _click_all_hamburger_menus_until_download(self, page: Page, target_dir: str) -> Optional[str]:
        """Click every visible NotebookLM hamburger/menu button until the PDF/PPTX
        download action appears. This intentionally includes the left-side source
        item menu shown in the screenshot, because that is the real menu that can
        expose the artifact download action in the current NotebookLM UI."""
        selectors = (
            "button.source-item-more-button",
            "button.artifact-more-button",
            "button[aria-label='المزيد']",
            "button[aria-label*='More']",
            "button[mattooltip='المزيد']",
            "button[title='المزيد']",
            "button:has(mat-icon:has-text('more_vert'))",
            "mat-icon:has-text('more_vert')",
        )

        for selector in selectors:
            try:
                locators = page.locator(selector)
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
                            button.locator("xpath=ancestor::button[1]").first.click(force=True)
                        except Exception:
                            continue

                    page.wait_for_timeout(400)
                    menu_items = page.locator(
                        "[role='menuitem']:has-text('تنزيل مستند PDF'), "
                        "[role='menuitem']:has-text('Download PDF'), "
                        "[role='menuitem']:has-text('Download'), "
                        "[role='menuitem']:has-text('تنزيل')"
                    )
                    if menu_items.count():
                        first_item = menu_items.first
                        if first_item.is_visible(timeout=1500):
                            return self._save_download(page, first_item, target_dir)

                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
            except Exception:
                continue

        return None
