"""Save the NotebookLM login by signing in yourself, in a normal Chrome window.

    npm run auth

Google asks the account owner to verify a sign-in (new device, 2-step verification, "is this you?"),
and it does not allow that to be done by an automated browser. So nothing here types into Google's
pages. This opens your own Chrome, with its own profile folder, and waits while *you* sign in and
finish whatever Google asks. It only looks afterwards: once Chrome holds a Google session and has
NotebookLM open, it saves that session for the worker and closes the window.

Chrome is started with a debugging port (a plain command-line option) so the session can be read; it is
not driven. If a Chrome is already listening on that port, the script attaches to it instead of opening one.
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from app.core.config import settings

DEFAULT_PORT = 9222


def default_profile_dir(environ=None) -> str:
    """Chrome's profile for this login lives in your home folder, not in the project: it holds your signed-in
    Google session, and nothing in the repository (or mounted into Docker) should."""
    environ = os.environ if environ is None else environ
    return environ.get("NOTEBOOKLM_CHROME_PROFILE", "").strip() or str(Path.home() / ".sard-ai" / "chrome-profile")
NOTEBOOKLM_HOST = "notebooklm.google.com"
# Cookies Google sets once an account is signed in.
GOOGLE_SESSION_COOKIES = {"SID", "__Secure-1PSID", "__Secure-3PSID"}


def find_chrome(environ=None, platform=None, exists=os.path.exists, which=shutil.which) -> Optional[str]:
    """Where Chrome is installed, or None. NOTEBOOKLM_CHROME_PATH overrides the search."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform

    override = environ.get("NOTEBOOKLM_CHROME_PATH", "").strip()
    if override:
        return override if exists(override) else None

    if platform == "darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif platform.startswith("win"):
        roots = [environ.get(name, "") for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        paths = [os.path.join(root, "Google", "Chrome", "Application", "chrome.exe") for root in roots if root]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            found = which(name)
            if found:
                return found
        return None

    return next((path for path in paths if exists(path)), None)


def chrome_command(chrome: str, profile_dir: str, port: int, url: str, extra: tuple[str, ...] = ()) -> list[str]:
    """Chrome as a person would start it, plus a debugging port and a profile folder of its own."""
    return [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        *extra,
        url,
    ]


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def signed_in(context) -> bool:
    """Does this Chrome hold a Google session and have NotebookLM open?

    NotebookLM shows a public landing page to signed-out visitors, so the page alone proves nothing;
    the Google session cookie is what shows a sign-in actually happened.
    """
    has_session = any(cookie["name"] in GOOGLE_SESSION_COOKIES for cookie in context.cookies())
    on_notebooklm = any(urlparse(page.url).hostname == NOTEBOOKLM_HOST for page in context.pages)
    return has_session and on_notebooklm


def capture_session(
    destination: str,
    chrome: Optional[str] = None,
    profile_dir: Optional[str] = None,
    port: int = DEFAULT_PORT,
    start_url: Optional[str] = None,
    ready: Callable = signed_in,
    timeout: float = 900,
    extra_args: tuple[str, ...] = (),
    say: Callable[[str], None] = print,
) -> str:
    """Wait for the user to sign in, then save the session to `destination`."""
    destination_path = Path(destination).resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile_dir or default_profile_dir()
    url = start_url or settings.NOTEBOOKLM_URL

    process = None
    if _port_is_open(port):
        say(f"Using the Chrome that is already listening on port {port}.")
    else:
        chrome = chrome or find_chrome()
        if not chrome:
            raise RuntimeError(
                "Could not find Google Chrome. Install it, or set NOTEBOOKLM_CHROME_PATH to its location."
            )
        process = subprocess.Popen(
            chrome_command(chrome, profile, port, url, extra_args),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            if _port_is_open(port):
                break
            if process.poll() is not None:
                raise RuntimeError("Chrome closed straight away. Close other Chrome windows that use the same profile and try again.")
            time.sleep(0.5)
        else:
            process.terminate()
            raise RuntimeError(f"Chrome did not start listening on port {port}.")

    say("")
    say("A Chrome window is open. In it:")
    say("  1. Sign in to Google, and finish any verification Google asks for.")
    say("  2. Make sure NotebookLM is open and you can see your notebooks.")
    say("This script only watches; it never types into Google's pages. It saves the session by itself.")
    say("")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            deadline = time.monotonic() + timeout
            while not ready(context):
                if time.monotonic() > deadline:
                    raise RuntimeError("Timed out waiting for the sign-in. Run `npm run auth` again when you are ready.")
                time.sleep(2)
            time.sleep(3)  # let NotebookLM finish setting its own cookies
            context.storage_state(path=str(destination_path))
            browser.close()  # only disconnects: the window is closed below
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    say(f"[SUCCESS] Session saved to: {destination_path}")
    return str(destination_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Save the NotebookLM login by signing in yourself in Chrome.")
    parser.add_argument("--port", type=int, default=int(os.getenv("NOTEBOOKLM_AUTH_PORT", DEFAULT_PORT)))
    parser.add_argument("--timeout", type=float, default=900, help="Seconds to wait for you to sign in")
    args = parser.parse_args()

    destination = Path(settings.NOTEBOOKLM_STORAGE_STATE_PATH).resolve()
    print("Google NotebookLM login for Sard-AI")
    print("=" * 64)
    print(f"The session will be saved to: {destination}")
    try:
        capture_session(str(destination), port=args.port, timeout=args.timeout)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
