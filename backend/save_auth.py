import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.config import settings


def _fill_input(page, selectors, value):
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible(timeout=2000):
            locator.fill(value)
            return True
    return False


def _click_button(page, selectors):
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() and locator.is_visible(timeout=2000):
            locator.click(force=True)
            return True
    return False


def ensure_notebooklm_session(storage_path: str | None = None) -> str:
    destination = Path(storage_path or settings.NOTEBOOKLM_STORAGE_STATE_PATH).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    email = (settings.NOTEBOOKLM_EMAIL or os.getenv("NOTEBOOKLM_EMAIL", "")).strip()
    password = (settings.NOTEBOOKLM_PASSWORD or os.getenv("NOTEBOOKLM_PASSWORD", "")).strip()

    if not email or not password:
        raise RuntimeError(
            "NotebookLM automation requires NOTEBOOKLM_EMAIL and NOTEBOOKLM_PASSWORD in the environment."
        )

    print("================================================================")
    print("Google NotebookLM Session Authenticator for Sard-AI")
    print("================================================================")
    print(f"Using account: {email}")
    print(f"Saving session to: {destination}")
    print("================================================================")

    browser = None
    with sync_playwright() as pw:
        # Decide whether to run headed or headless. If no DISPLAY is present
        # or the env var NOTEBOOKLM_HEADLESS is set, prefer headless mode.
        headless_env = os.getenv("NOTEBOOKLM_HEADLESS", "").lower() in ("1", "true", "yes")
        display = os.getenv("DISPLAY")
        prefer_headless = headless_env or not display

        for channel in ["chrome", "msedge", None]:
            try:
                kwargs = {
                    "headless": prefer_headless is True and True or False,
                    "ignore_default_args": ["--enable-automation"],
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                }
                if channel:
                    kwargs["channel"] = channel
                browser = pw.chromium.launch(**kwargs)
                print(f"[INFO] Successfully launched browser channel: {channel or 'default chromium'}")
                break
            except Exception as exc:
                print(f"[WARN] Channel '{channel}' launch failed: {exc}")

        if not browser:
            raise RuntimeError("Could not launch Chromium browser for NotebookLM auth.")

        context = browser.new_context(
            viewport={"width": 1440, "height": 980},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)

        email_filled = _fill_input(
            page,
            [
                "input[type='email']",
                "input[name='identifier']",
                "input[name='Email']",
                "textarea[name='identifier']",
            ],
            email,
        )
        if not email_filled:
            raise RuntimeError("Could not locate the Google email input.")

        if not _click_button(
            page,
            [
                "#identifierNext",
                "button:has-text('Next')",
                "button:has-text('التالي')",
                "button[type='button']",
            ],
        ):
            page.keyboard.press("Tab")
            page.keyboard.press("Enter")

        page.wait_for_timeout(3000)

        password_filled = _fill_input(
            page,
            [
                "input[type='password']",
                "input[name='Passwd']",
                "input[name='password']",
            ],
            password,
        )
        if not password_filled:
            raise RuntimeError("Could not locate the Google password input.")

        if not _click_button(
            page,
            [
                "#passwordNext",
                "button:has-text('Next')",
                "button:has-text('التالي')",
                "button[type='button']",
            ],
        ):
            page.keyboard.press("Tab")
            page.keyboard.press("Enter")

        page.wait_for_timeout(5000)

        page.goto("https://notebooklm.google.com", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(7000)

        for selector in (
            "text=Continue",
            "text=استمرار",
            "button:has-text('Continue')",
            "button:has-text('استمرار')",
            "button:has-text('I agree')",
            "button:has-text('أوافق')",
        ):
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=2000):
                    locator.click(force=True)
            except Exception:
                pass

        page.wait_for_timeout(3000)
        context.storage_state(path=str(destination))
        print(f"[SUCCESS] Google authentication session saved to: {destination}")
        return str(destination)


def main():
    ensure_notebooklm_session()


if __name__ == "__main__":
    main()
