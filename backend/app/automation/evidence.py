import logging
import os
from pathlib import Path

from playwright.sync_api import Page


logger = logging.getLogger(__name__)


def capture_evidence(page: Page, base_dir: str, step: str, error: BaseException) -> str:
    """Save a screenshot, the page DOM and the error text for a failed step.

    Never raises: evidence is best effort and must not hide the real error.
    """
    step_dir = os.path.join(base_dir, step)
    try:
        os.makedirs(step_dir, exist_ok=True)
    except OSError as exc:
        logger.warning("[Sard] Could not create evidence folder %s: %s", step_dir, exc)
        return step_dir

    try:
        Path(step_dir, "error.txt").write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("[Sard] Could not save error text: %s", exc)
    try:
        page.screenshot(path=os.path.join(step_dir, "screenshot.png"), full_page=True)
    except Exception as exc:
        logger.warning("[Sard] Could not capture screenshot: %s", exc)
    try:
        Path(step_dir, "page.html").write_text(page.content(), encoding="utf-8")
    except Exception as exc:
        logger.warning("[Sard] Could not save page HTML: %s", exc)
    return step_dir
