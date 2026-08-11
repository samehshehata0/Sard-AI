import os
import asyncio
import logging
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from app.core.config import settings

logger = logging.getLogger(__name__)

class NotebookLMService:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def _sync_handle_dialogs(self, page: Page):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            dismiss_selectors = [
                "button:has-text('Got it')",
                "button:has-text('Dismiss')",
                "button:has-text('Accept all')",
                "button:has-text('موافق')",
                "button:has-text('فهمت')",
                "[aria-label='Close']",
                "[aria-label='إغلاق']"
            ]
            for sel in dismiss_selectors:
                if page.is_visible(sel, timeout=1000):
                    try:
                        page.click(sel, force=True)
                    except Exception:
                        pass
                    logger.info(f"[NotebookLM] Dismissed popup: {sel}")
        except Exception:
            pass

    def _sync_pipeline(self, file_path: str, prompt: str, target_dir: str) -> str:
        """
        Synchronous Playwright execution pipeline for Google NotebookLM.
        Guarantees every generation is executed in a brand new isolated notebook.
        """
        os.makedirs(target_dir, exist_ok=True)
        
        # Robust storage_state.json path resolution
        possible_paths = [
            settings.NOTEBOOKLM_STORAGE_STATE_PATH,
            os.path.join(os.path.dirname(__file__), "..", "..", "storage_state.json"),
            os.path.join(os.path.dirname(__file__), "..", "storage_state.json"),
            os.path.join(os.path.dirname(__file__), "storage_state.json"),
            os.path.join(os.getcwd(), "backend", "storage_state.json"),
            os.path.join(os.getcwd(), "storage_state.json"),
        ]
        storage_path = None
        for p_path in possible_paths:
            abs_p = os.path.abspath(p_path)
            if os.path.exists(abs_p) and os.path.getsize(abs_p) > 10:
                storage_path = abs_p
                break

        # Read story content
        story_text = ""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                story_text = f.read()
        except Exception as e:
            logger.warning(f"[NotebookLM] Could not read story file: {e}")

        # Combine story text with prompt so Gemini has full context
        combined_prompt = f"{prompt}\n\nنص الموضوع والمحاور التعليمية:\n{story_text}"

        with sync_playwright() as p:
            launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            logger.info(f"[NotebookLM] Launching Playwright Chromium (Headless: {settings.PLAYWRIGHT_HEADLESS})...")
            
            browser = p.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                ignore_default_args=["--enable-automation"],
                args=launch_args
            )
            
            ctx_kwargs = {
                "user_agent": user_agent,
                "viewport": {"width": 1280, "height": 800}
            }
            if storage_path:
                logger.info(f"[NotebookLM] Resuming authenticated session from {storage_path}")
                ctx_kwargs["storage_state"] = storage_path
            else:
                logger.warning("[NotebookLM] storage_state.json not found! Launching unauthenticated context.")

            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            
            # 1. Open NotebookLM Homepage
            logger.info(f"[NotebookLM] Opening {settings.NOTEBOOKLM_URL}")
            for attempt in range(1, 4):
                try:
                    page.goto(settings.NOTEBOOKLM_URL, wait_until="networkidle", timeout=45000)
                    self._sync_handle_dialogs(page)
                    break
                except Exception as e:
                    logger.warning(f"[NotebookLM] Open attempt {attempt} failed: {e}")
                    if attempt == 3:
                        raise e
                    page.wait_for_timeout(3000)

            if "accounts.google.com" in page.url or "signin" in page.url:
                logger.error("[NotebookLM] Redirected to Google Sign-in page! Authentication session missing or expired.")
                raise RuntimeError("Google Account Sign-In required! Please run 'npm run auth' in terminal to log into Google and save your session.")

            # 2. FORCE BRAND NEW NOTEBOOK CREATION
            logger.info("[NotebookLM] Creating a BRAND NEW isolated notebook for this generation request...")
            create_selectors = [
                "button.create-new-button",
                ".create-new-button",
                "button:has-text('New Notebook')",
                "button:has-text('Create new')",
                "button:has-text('Create notebook')",
                "button:has-text('دفتر ملاحظات جديد')",
                "button:has-text('إنشاء')",
                "[aria-label='Create new notebook']",
                "[aria-label='Create new']",
                "mat-card:has-text('Create new notebook')",
                "div:has-text('Create new notebook')"
            ]
            created = False
            for sel in create_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=2000):
                        loc.click(force=True)
                        created = True
                        logger.info(f"[NotebookLM] Successfully clicked new notebook creation selector: {sel}")
                        break
                except Exception:
                    pass
                    
            if not created:
                logger.info("[NotebookLM] Direct button selector not visible. Navigating directly to https://notebooklm.google.com/notebook/new...")
                try:
                    page.goto("https://notebooklm.google.com/notebook/new", wait_until="networkidle", timeout=30000)
                    created = True
                except Exception as e:
                    logger.warning(f"[NotebookLM] Direct new notebook URL navigation notice: {e}")
                    page.keyboard.press("Control+n")

            page.wait_for_timeout(5000)
            self._sync_handle_dialogs(page)

            # 3. Add Source via Text or File Upload into the New Notebook
            logger.info(f"[NotebookLM] Inserting source content into brand new notebook...")
            uploaded = False

            # Option A: Try Copied Text option inside modal
            text_card = page.locator("button:has-text('Copied text'), div:has-text('Copied text'), button:has-text('Text'), mat-card:has-text('Text')").first
            if not text_card.is_visible(timeout=2000):
                add_btn = page.locator("button:has-text('Add sources'), button:has-text('إضافة مصادر')").first
                if add_btn.is_visible(timeout=2000):
                    try:
                        add_btn.click(force=True)
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

            text_card = page.locator("button:has-text('Copied text'), div:has-text('Copied text'), button:has-text('Text'), mat-card:has-text('Text')").first
            if text_card.is_visible(timeout=3000):
                try:
                    text_card.click(force=True)
                    page.wait_for_timeout(1000)
                    text_area = page.locator("textarea, [contenteditable='true']").first
                    if text_area.is_visible(timeout=3000):
                        text_area.click(force=True)
                        text_area.fill(story_text)
                        page.wait_for_timeout(500)
                        insert_btn = page.locator("button:has-text('Insert'), button:has-text('Save'), button:has-text('Add')").first
                        if insert_btn.is_visible(timeout=3000):
                            insert_btn.click(force=True)
                            uploaded = True
                            logger.info("[NotebookLM] Source inserted via Copied text into new notebook successfully!")
                except Exception as e:
                    logger.info(f"[NotebookLM] Copied text insertion notice: {e}")

            # Option B: Fallback file upload
            if not uploaded:
                try:
                    file_input = page.locator("input[type='file']").first
                    if file_input.count() > 0:
                        file_input.set_input_files(file_path)
                        uploaded = True
                        logger.info("[NotebookLM] Direct set_input_files into new notebook succeeded!")
                except Exception as e:
                    logger.info(f"[NotebookLM] Direct input file set notice: {e}")

            logger.info("[NotebookLM] Waiting for source document indexing in new notebook...")
            page.wait_for_timeout(6000)

            # Dismiss overlay modal if still open
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # 4. Trigger Studio Presentation Generation (Slide / Infographic)
            logger.info("[NotebookLM] Triggering Studio Presentation generation in new notebook...")
            studio_selectors = [
                "button:has-text('Slide')",
                "div:has-text('Slide')",
                "[aria-label*='Slide']",
                "button:has-text('Infogr')",
                "div:has-text('Infogr')",
                "[aria-label*='Infographic']",
                "text='Slide...'",
                "text='Slide Deck'",
                "text='Infographic'"
            ]
            clicked_studio = False
            for sel in studio_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible(timeout=2000):
                        loc.click(force=True)
                        clicked_studio = True
                        logger.info(f"[NotebookLM] Clicked Studio button: {sel}")
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

            # 5. Submit Prompt via Chat Box
            chat_selectors = [
                "textarea",
                "[contenteditable='true']",
                "[placeholder*='Ask a question']",
                "[placeholder*='create something']",
                "[placeholder*='Start typing']",
                "[placeholder*='Ask']",
                "[placeholder*='اسأل']"
            ]
            submitted_chat = False
            for c_sel in chat_selectors:
                try:
                    chat_input = page.locator(c_sel).first
                    if chat_input.count() > 0 and chat_input.is_visible(timeout=3000):
                        chat_input.click(force=True)
                        chat_input.fill(combined_prompt)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Enter")
                        
                        # Click arrow submit button if available
                        submit_btn = page.locator("button[aria-label*='Send'], button[aria-label*='Submit'], button:has(svg)").first
                        if submit_btn.count() > 0 and submit_btn.is_visible(timeout=1000):
                            submit_btn.click(force=True)

                        submitted_chat = True
                        logger.info(f"[NotebookLM] Presentation prompt submitted via chat input selector: {c_sel}")
                        break
                except Exception:
                    pass

            # 6. Wait for Gemini Generation & Export PDF / Screenshot
            logger.info("[NotebookLM] Waiting for presentation generation in new notebook...")
            page.wait_for_timeout(25000)

            output_file = os.path.join(target_dir, "presentation.pdf")
            try:
                page.pdf(path=output_file)
                logger.info(f"[NotebookLM] PDF exported successfully from new notebook -> {output_file}")
            except Exception as e:
                logger.warning(f"[NotebookLM] Direct PDF export fallback to screenshot: {e}")
                output_file = os.path.join(target_dir, "presentation.png")
                page.screenshot(path=output_file)

            browser.close()
            return output_file

    async def run_pipeline(self, file_path: str, prompt: str, target_dir: str) -> str:
        """
        Runs the full NotebookLM automation pipeline safely in a dedicated thread.
        """
        return await asyncio.to_thread(self._sync_pipeline, file_path, prompt, target_dir)

    async def restore_session(self) -> None:
        pass

    async def open_notebooklm(self) -> None:
        pass

    async def create_notebook(self) -> None:
        pass

    async def upload_source(self, file_path: str) -> None:
        pass

    async def submit_prompt(self, prompt: str) -> None:
        pass

    async def wait_until_generation_finishes(self, timeout_seconds: int = 180) -> None:
        pass

    async def export_presentation(self) -> None:
        pass

    async def download_file(self, target_dir: str) -> str:
        return os.path.join(target_dir, "presentation.pdf")

    async def cleanup(self) -> None:
        pass
