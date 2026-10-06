"""Tell a person that something needs them.

Used when the NotebookLM login has expired (or is about to) and when the quota runs out. Every channel is
best effort: a failing notification must never break the job or worker that triggered it, so nothing here
raises. Messages never contain credentials.
"""
import logging
import subprocess
import sys
from typing import Callable, Optional

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


def _applescript_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def desktop_command(title: str, message: str, platform: Optional[str] = None) -> Optional[list[str]]:
    """The command that shows a desktop notification on this system, or None where there is no simple one."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        script = f'display notification "{_applescript_quote(message)}" with title "{_applescript_quote(title)}"'
        return ["osascript", "-e", script]
    if platform.startswith("linux"):
        return ["notify-send", title, message]
    return None


def notify(
    title: str,
    message: str,
    webhook: Optional[str] = None,
    desktop: Optional[bool] = None,
    run: Callable = subprocess.run,
    post: Callable = httpx.post,
) -> list[str]:
    """Send the notification on every configured channel. Returns the channels that worked."""
    webhook = settings.NOTIFY_WEBHOOK_URL if webhook is None else webhook
    desktop = settings.NOTIFY_DESKTOP if desktop is None else desktop

    logger.warning("[Sard] NOTIFY: %s: %s", title, message)
    delivered = ["log"]

    if desktop:
        command = desktop_command(title, message)
        if command:
            try:
                run(command, check=True, capture_output=True, timeout=10)
                delivered.append("desktop")
            except Exception as exc:
                logger.info("[Sard] Desktop notification was not shown: %s", exc)

    if webhook:
        try:
            response = post(
                webhook,
                json={"title": title, "message": message, "text": f"{title}: {message}", "content": f"**{title}**\n{message}"},
                timeout=10,
            )
            response.raise_for_status()
            delivered.append("webhook")
        except Exception as exc:
            logger.warning("[Sard] Webhook notification failed: %s", exc)

    return delivered
