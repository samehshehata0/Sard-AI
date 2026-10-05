import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from playwright.sync_api import Locator, Page


logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 250


class LocatorNotFoundError(RuntimeError):
    """No strategy for a registered UI element matched a visible element in time."""


class LocatorValidationError(RuntimeError):
    """An element was found but is not the one we expect, so we must not act on it."""


@dataclass(frozen=True)
class Strategy:
    name: str
    selector: str


@dataclass(frozen=True)
class Resolved:
    key: str
    strategy: str
    locator: Locator


Validator = Callable[[Locator], None]


class LocatorRegistry:
    """Ordered locator strategies per UI element, behind one resolver.

    Strategies are tried most-stable first (relative XPath, then absolute
    XPath, then role/aria, then visible text). The resolver records which
    strategy matched so UI drift shows up in the logs before it breaks us.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, tuple[Strategy, ...]] = {}
        self._validators: dict[str, Validator] = {}

    def register(
        self,
        key: str,
        strategies: tuple[Strategy, ...],
        validator: Optional[Validator] = None,
    ) -> None:
        self._strategies[key] = strategies
        if validator is not None:
            self._validators[key] = validator

    def strategies(self, key: str) -> tuple[Strategy, ...]:
        return self._strategies[key]

    def resolve(self, page: Page, key: str, timeout_ms: int = 10_000) -> Resolved:
        strategies = self._strategies[key]
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            for strategy in strategies:
                locator = page.locator(strategy.selector).first
                try:
                    matched = locator.count() > 0 and locator.is_visible()
                except Exception:
                    matched = False
                if not matched:
                    continue
                validator = self._validators.get(key)
                if validator is not None:
                    validator(locator)
                logger.info("[Sard] Locator '%s' matched via %s", key, strategy.name)
                return Resolved(key=key, strategy=strategy.name, locator=locator)
            if time.monotonic() >= deadline:
                tried = ", ".join(s.name for s in strategies)
                raise LocatorNotFoundError(f"No locator strategy matched '{key}' (tried: {tried})")
            page.wait_for_timeout(POLL_INTERVAL_MS)
