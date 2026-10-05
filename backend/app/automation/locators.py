import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional, Union

from playwright.sync_api import Locator, Page


logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 250

Scope = Union[Page, Locator]


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


@dataclass(frozen=True)
class Element:
    key: str
    strategies: tuple[Strategy, ...]
    pick: str = "first"
    # Where the element lives, so a canary knows when it can check it:
    # "home", "notebook", or a dialog name that needs a click to open.
    screen: str = "notebook"
    validator: Optional[Validator] = None
    # The canary treats a missing required element as a failure; the others
    # only appear in some states (a finished deck, a first-run welcome page).
    required: bool = False
    # Hidden inputs (file pickers) only need to exist in the DOM.
    hidden_ok: bool = False


def tiered(
    structure: tuple[str, ...] = (),
    aria: tuple[str, ...] = (),
    icon: tuple[str, ...] = (),
    text: tuple[str, ...] = (),
) -> tuple[Strategy, ...]:
    """Build strategies most-stable first: DOM structure, aria, icon name, visible text."""
    strategies: list[Strategy] = []
    for tier, selectors in (("structure", structure), ("aria", aria), ("icon", icon), ("text", text)):
        for index, selector in enumerate(selectors, start=1):
            strategies.append(Strategy(f"{tier}-{index}", selector))
    return tuple(strategies)


class LocatorRegistry:
    """Ordered locator strategies per UI element, behind one resolver.

    Strategies are tried most-stable first (XPath/structure, then aria, then
    icon name, then visible text). The resolver records which strategy matched
    so UI drift shows up in the logs before it breaks us.
    """

    def __init__(self) -> None:
        self._elements: dict[str, Element] = {}

    def register(
        self,
        key: str,
        strategies: tuple[Strategy, ...],
        validator: Optional[Validator] = None,
        pick: str = "first",
        screen: str = "notebook",
        required: bool = False,
        hidden_ok: bool = False,
    ) -> None:
        self._elements[key] = Element(
            key,
            strategies,
            pick=pick,
            screen=screen,
            validator=validator,
            required=required,
            hidden_ok=hidden_ok,
        )

    def keys(self) -> tuple[str, ...]:
        return tuple(self._elements)

    def element(self, key: str) -> Element:
        return self._elements[key]

    def strategies(self, key: str) -> tuple[Strategy, ...]:
        return self._elements[key].strategies

    def candidates(
        self,
        scope: Scope,
        key: str,
        params: Optional[dict[str, str]] = None,
    ) -> Iterator[tuple[Strategy, Locator]]:
        """Each strategy's locator in order, for callers that act on every match."""
        element = self._elements[key]
        for strategy in element.strategies:
            selector = strategy.selector
            for name, value in (params or {}).items():
                selector = selector.replace("{" + name + "}", value)
            locator = scope.locator(selector)
            yield strategy, (locator.last if element.pick == "last" else locator.first)

    def all_matches(
        self,
        scope: Scope,
        key: str,
        params: Optional[dict[str, str]] = None,
    ) -> Iterator[tuple[Strategy, Locator]]:
        """Each strategy's unpicked locator, for callers that walk every match."""
        for strategy in self._elements[key].strategies:
            selector = strategy.selector
            for name, value in (params or {}).items():
                selector = selector.replace("{" + name + "}", value)
            yield strategy, scope.locator(selector)

    def find(
        self,
        scope: Scope,
        key: str,
        params: Optional[dict[str, str]] = None,
    ) -> Optional[Resolved]:
        """One pass: the first visible match, or None. Never waits."""
        element = self._elements[key]
        for strategy, locator in self.candidates(scope, key, params):
            try:
                matched = locator.count() > 0 and locator.is_visible()
            except Exception:
                matched = False
            if not matched:
                continue
            if element.validator is not None:
                element.validator(locator)
            logger.info("[Sard] Locator '%s' matched via %s", key, strategy.name)
            return Resolved(key=key, strategy=strategy.name, locator=locator)
        return None

    def resolve(
        self,
        page: Page,
        key: str,
        timeout_ms: int = 10_000,
        scope: Optional[Scope] = None,
        params: Optional[dict[str, str]] = None,
    ) -> Resolved:
        """Wait until some strategy matches a visible element, or raise."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            resolved = self.find(scope if scope is not None else page, key, params)
            if resolved is not None:
                return resolved
            if time.monotonic() >= deadline:
                tried = ", ".join(s.name for s in self.strategies(key))
                raise LocatorNotFoundError(f"No locator strategy matched '{key}' (tried: {tried})")
            page.wait_for_timeout(POLL_INTERVAL_MS)
