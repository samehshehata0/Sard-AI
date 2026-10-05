import logging
from typing import Callable, Optional, TypeVar

from playwright.sync_api import Page

from app.automation.errors import (
    NeedsLoginError,
    NotebookLMGenerationError,
    QuotaExhaustedError,
    TransientStepError,
)
from app.automation.evidence import capture_evidence


logger = logging.getLogger(__name__)

T = TypeVar("T")

# A condition returns False (or raises) when it does not hold.
Condition = Callable[[], Optional[bool]]


def wait_until(page: Page, predicate: Callable[[], bool], timeout_ms: int = 15_000, interval_ms: int = 250) -> bool:
    """Poll a condition until it holds or the time runs out. No fixed sleeps."""
    waited = 0
    while True:
        try:
            if predicate():
                return True
        except Exception:
            pass
        if waited >= timeout_ms:
            return False
        page.wait_for_timeout(interval_ms)
        waited += interval_ms


def wait_until_stable(
    page: Page,
    predicate: Callable[[], bool],
    stable_ms: int,
    timeout_ms: int = 30_000,
    interval_ms: int = 500,
) -> bool:
    """Wait until a condition has held continuously for `stable_ms`.

    A condition that flips back resets the clock, so a control that is only
    briefly enabled does not count as ready.
    """
    waited = 0
    holding_since: Optional[int] = None
    while True:
        try:
            holds = bool(predicate())
        except Exception:
            holds = False
        if holds:
            if holding_since is None:
                holding_since = waited
            if waited - holding_since >= stable_ms:
                return True
        else:
            holding_since = None
        if waited >= timeout_ms:
            return False
        page.wait_for_timeout(interval_ms)
        waited += interval_ms


def check_session(page: Page, quota_markers: tuple[str, ...] = ()) -> None:
    """Raise a typed error if the page shows an expired login or a quota refusal."""
    if "accounts.google.com" in page.url or "signin" in page.url:
        raise NeedsLoginError("NotebookLM authentication session expired")
    for marker in quota_markers:
        try:
            refusal = page.locator(f"text={marker}").first
            if refusal.count() > 0 and refusal.is_visible():
                raise QuotaExhaustedError(f"NotebookLM refused to create a slide deck: '{marker}'")
        except QuotaExhaustedError:
            raise
        except Exception:
            continue


def _require(condition: Condition, step: str, kind: str) -> None:
    try:
        holds = condition()
    except NotebookLMGenerationError:
        raise
    except Exception as exc:
        raise TransientStepError(f"Step '{step}' {kind} could not be checked: {exc}") from exc
    if holds is False:
        raise TransientStepError(f"Step '{step}' {kind} did not hold")


def run_step(
    page: Page,
    name: str,
    action: Callable[[], T],
    *,
    pre: Optional[Condition] = None,
    post: Optional[Condition] = None,
    evidence_dir: Optional[str] = None,
    quota_markers: tuple[str, ...] = (),
) -> T:
    """Run one automation step as precondition, action, postcondition.

    The step only counts as done once its effect is observed. Every failure
    leaves as a typed NotebookLMGenerationError with evidence saved beside it.
    """
    try:
        check_session(page, quota_markers)
        if pre is not None:
            _require(pre, name, "precondition")
        result = action()
        check_session(page, quota_markers)
        if post is not None:
            _require(post, name, "postcondition")
        logger.info("[Sard] NotebookLM step '%s' done", name)
        return result
    except NotebookLMGenerationError as exc:
        _attach_evidence(page, name, exc, evidence_dir)
        raise
    except Exception as exc:
        typed = TransientStepError(f"Step '{name}' failed: {exc}")
        typed.__cause__ = exc
        _attach_evidence(page, name, typed, evidence_dir)
        raise typed from exc


def _attach_evidence(page: Page, step: str, error: NotebookLMGenerationError, base_dir: Optional[str]) -> None:
    if base_dir is None or error.evidence_dir is not None:
        return
    error.evidence_dir = capture_evidence(page, base_dir, step, error)
    logger.error("[Sard] NotebookLM step '%s' failed (%s); evidence saved to %s", step, error, error.evidence_dir)
