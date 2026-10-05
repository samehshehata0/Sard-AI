import random
from typing import Optional

from playwright.sync_api import Locator, Page


class HumanPacer:
    """Makes the browser behave less like a script: short random pauses, a real
    mouse move before each click, and long text entered in pieces.

    This is a deliberate, configurable layer. Waiting for the page to be ready
    is a separate job done by condition waits; nothing here decides readiness.
    With `enabled=False` every method does the plain, instant thing, which is
    what tests use.
    """

    def __init__(
        self,
        enabled: bool = True,
        min_ms: int = 400,
        max_ms: int = 1500,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.enabled = enabled
        low, high = sorted((min_ms, max_ms))
        self.min_ms = max(0, low)
        self.max_ms = max(0, high)
        self._rng = rng or random.Random()

    @classmethod
    def from_settings(cls, settings) -> "HumanPacer":
        return cls(
            enabled=settings.NOTEBOOKLM_HUMAN_PACING,
            min_ms=settings.NOTEBOOKLM_PACING_MIN_MS,
            max_ms=settings.NOTEBOOKLM_PACING_MAX_MS,
        )

    def pause(self, page: Page, low_ms: Optional[int] = None, high_ms: Optional[int] = None) -> None:
        if not self.enabled:
            return
        low = self.min_ms if low_ms is None else low_ms
        high = self.max_ms if high_ms is None else high_ms
        page.wait_for_timeout(self._rng.randint(min(low, high), max(low, high)))

    def click(self, page: Page, locator: Locator, force: bool = True) -> None:
        """Pause, move the mouse to a point on the element, then click there."""
        if not self.enabled:
            locator.click(force=force)
            return
        self.pause(page)
        position = None
        try:
            locator.scroll_into_view_if_needed(timeout=2000)
            box = locator.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                position = {
                    "x": box["width"] * self._rng.uniform(0.3, 0.7),
                    "y": box["height"] * self._rng.uniform(0.3, 0.7),
                }
                page.mouse.move(
                    box["x"] + position["x"],
                    box["y"] + position["y"],
                    steps=self._rng.randint(8, 20),
                )
                self.pause(page, 120, 400)
        except Exception:
            position = None
        if position is not None:
            locator.click(force=force, position=position)
        else:
            locator.click(force=force)

    def type_text(self, page: Page, locator: Locator, text: str) -> None:
        """Enter text in pieces with short pauses, like pasting a few passages.

        Disabled, it is a plain fill. Pieces are inserted as text rather than
        key by key, which keeps Arabic and other right-to-left input reliable.
        """
        if not self.enabled or len(text) <= 120:
            locator.fill(text)
            return
        self.click(page, locator)
        locator.fill("")
        index = 0
        while index < len(text):
            size = self._rng.randint(80, 240)
            page.keyboard.insert_text(text[index : index + size])
            index += size
            if index < len(text):
                self.pause(page, 80, 300)
