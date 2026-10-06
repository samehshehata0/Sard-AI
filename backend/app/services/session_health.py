"""Is the saved NotebookLM login still good, and for how long?

Reads the saved Playwright session (`npm run auth` writes it). The Google session cookies carry an
expiry time, so the earliest of them tells how long the login should last, which lets us warn a person
before it runs out instead of after jobs have started to wait. Whether Google has already ended the
session on its side can only be found out by visiting NotebookLM; the worker does that now and then.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings

# Cookies Google sets once an account is signed in.
GOOGLE_SESSION_COOKIES = {"SID", "__Secure-1PSID", "__Secure-3PSID"}


def session_health(
    path: Optional[str] = None,
    now: Optional[datetime] = None,
    warn_days: Optional[float] = None,
) -> dict[str, Any]:
    """The state of the saved login: missing, invalid, expired, expiring or ok.

    `expires_at` is the earliest expiry among the Google session cookies; a login made only of session
    cookies (no expiry) has none, and counts as ok until a visit shows otherwise.
    """
    from app.services.notebooklm_service import storage_state_candidates  # imported late: it pulls in Playwright

    now = now or datetime.now(timezone.utc)
    warn = timedelta(days=settings.NOTEBOOKLM_SESSION_WARN_DAYS if warn_days is None else warn_days)

    candidates = [path] if path else storage_state_candidates()
    file = next((p for p in candidates if os.path.isfile(p) and os.path.getsize(p) > 10), None)
    if file is None:
        return {"state": "missing", "expires_at": None, "days_left": None}

    try:
        with open(file, encoding="utf-8") as handle:
            cookies = json.load(handle).get("cookies", [])
    except (OSError, ValueError):
        return {"state": "invalid", "expires_at": None, "days_left": None}

    session = [c for c in cookies if c.get("name") in GOOGLE_SESSION_COOKIES]
    if not session:
        return {"state": "invalid", "expires_at": None, "days_left": None}

    expiries = [c["expires"] for c in session if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0]
    if not expiries:
        return {"state": "ok", "expires_at": None, "days_left": None}

    expires_at = datetime.fromtimestamp(min(expiries), tz=timezone.utc)
    days_left = (expires_at - now).total_seconds() / 86400
    if expires_at <= now:
        state = "expired"
    elif expires_at - now <= warn:
        state = "expiring"
    else:
        state = "ok"
    return {"state": state, "expires_at": expires_at.isoformat(), "days_left": round(days_left, 2)}
