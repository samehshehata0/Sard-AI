import logging

from playwright.sync_api import Locator, Page

from app.automation.errors import PermanentStepError, TransientStepError
from app.automation.locators import (
    LocatorNotFoundError,
    LocatorRegistry,
    LocatorValidationError,
    Strategy,
)


logger = logging.getLogger(__name__)

DIALOG = "configurable-form-dialog"

GENERATE_NOW = "slide_deck.generate_now"
GENERATING_INDICATOR = "slide_deck.generating_indicator"

LATER_LABEL_MARKERS = ("later", "لاحق")


class GenerateNowError(TransientStepError):
    """Generate now could not be chosen, or generation did not visibly start."""


class GenerateNowLayoutError(PermanentStepError):
    """The dialog does not look like we expect, so clicking could pick the wrong action."""


def _require_last_of_two_actions(button: Locator) -> None:
    """Generate now is the last dialog action, after Generate later.

    Refuse to act on anything else: clicking the wrong action silently defers
    the whole Slide Deck.
    """
    layout = button.evaluate(
        """el => {
            const actions = el.closest('mat-dialog-actions');
            const buttons = actions ? Array.from(actions.querySelectorAll('button')) : [];
            return {
                count: buttons.length,
                isLast: buttons[buttons.length - 1] === el,
                label: (el.textContent || '').trim(),
            };
        }"""
    )
    if layout["count"] < 2 or not layout["isLast"]:
        raise LocatorValidationError(
            "Unexpected Slide Deck dialog layout: expected Generate now as the last of "
            f"at least two actions (actions={layout['count']}, last={layout['isLast']})"
        )
    label = layout["label"].lower()
    if any(marker in label for marker in LATER_LABEL_MARKERS):
        raise LocatorValidationError(
            f"Unexpected Slide Deck dialog layout: last action is labelled '{layout['label']}', "
            "which looks like Generate later"
        )


def build_registry() -> LocatorRegistry:
    registry = LocatorRegistry()
    registry.register(
        GENERATE_NOW,
        (
            # Parentheses matter: each nb-button is the only one in its own span,
            # so nb-button[last()] would match Generate later as well.
            Strategy(
                "relative-xpath",
                f"xpath=(//{DIALOG}//mat-dialog-actions//nb-button/button)[last()]",
            ),
            Strategy(
                "absolute-xpath",
                "xpath=/html/body/div[8]/div/div[2]/mat-dialog-container/div/div/"
                f"{DIALOG}/div/mat-dialog-actions/span/span[2]/nb-button/button",
            ),
            Strategy("role-last-action", f"{DIALOG} mat-dialog-actions button >> nth=-1"),
            Strategy(
                "text",
                f"{DIALOG} mat-dialog-actions button:has-text('Generate')"
                ":not(:has-text('later')):not(:has-text('لاحق'))",
            ),
        ),
        validator=_require_last_of_two_actions,
    )
    registry.register(
        GENERATING_INDICATOR,
        (
            Strategy("text-ar", "text=جارٍ إنشاء مجموعة الشرائح"),
            Strategy("text-en", "text=Creating slide deck"),
        ),
    )
    return registry


def click_generate_now(
    page: Page,
    registry: LocatorRegistry,
    find_timeout_ms: int = 10_000,
    started_timeout_ms: int = 60_000,
) -> str:
    """Click Generate now and confirm generation visibly started.

    Returns the name of the locator strategy that matched.
    """
    try:
        resolved = registry.resolve(page, GENERATE_NOW, timeout_ms=find_timeout_ms)
    except LocatorValidationError as exc:
        raise GenerateNowLayoutError(str(exc)) from exc
    except LocatorNotFoundError as exc:
        raise GenerateNowError(str(exc)) from exc

    # The action may stay disabled until the form is ready; wait, don't force.
    for _ in range(max(1, find_timeout_ms // 250)):
        if resolved.locator.is_enabled():
            break
        page.wait_for_timeout(250)
    else:
        raise GenerateNowError("Generate now stayed disabled")

    resolved.locator.click()

    try:
        page.locator(DIALOG).first.wait_for(state="hidden", timeout=started_timeout_ms)
    except Exception as exc:
        raise GenerateNowError("Slide Deck dialog did not close after Generate now") from exc
    try:
        registry.resolve(page, GENERATING_INDICATOR, timeout_ms=started_timeout_ms)
    except LocatorNotFoundError as exc:
        raise GenerateNowError(
            "Dialog closed but NotebookLM never showed the slide deck as generating"
        ) from exc

    logger.info("[Sard] NotebookLM slide deck generation started (Generate now via %s)", resolved.strategy)
    return resolved.strategy
