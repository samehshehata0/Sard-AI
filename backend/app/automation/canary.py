from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import Page

from app.automation.locators import LocatorRegistry


@dataclass(frozen=True)
class CanaryResult:
    key: str
    screen: str
    status: str  # "ok", "degraded", "missing" or "skipped"
    matched: tuple[str, ...] = ()
    primary: Optional[str] = None
    required: bool = False

    @property
    def failed(self) -> bool:
        return self.status == "missing" and self.required


def run_canary(page: Page, registry: LocatorRegistry, screens: set[str]) -> list[CanaryResult]:
    """Check which locator strategies match on the page, without clicking anything.

    Elements on other screens (dialogs, finished artifacts) are skipped, since
    reaching them would mean clicking through the product.
    """
    results: list[CanaryResult] = []
    for key in registry.keys():
        element = registry.element(key)
        primary = element.strategies[0].name
        if element.screen not in screens:
            results.append(CanaryResult(key, element.screen, "skipped", primary=primary))
            continue

        matched: list[str] = []
        for strategy, locator in registry.all_matches(page, key):
            try:
                if locator.count() > 0 and (element.hidden_ok or locator.first.is_visible()):
                    matched.append(strategy.name)
            except Exception:
                continue

        if not matched:
            status = "missing"
        elif matched[0] != primary:
            status = "degraded"
        else:
            status = "ok"
        results.append(
            CanaryResult(key, element.screen, status, tuple(matched), primary, element.required)
        )
    return results


def format_report(results: list[CanaryResult]) -> str:
    lines = []
    for result in results:
        if result.status == "skipped":
            lines.append(f"SKIP      {result.key}  (needs the '{result.screen}' screen)")
        elif result.status == "ok":
            lines.append(f"OK        {result.key}  via {result.matched[0]}")
        elif result.status == "degraded":
            lines.append(
                f"DRIFT     {result.key}  primary '{result.primary}' no longer matches; "
                f"only fallbacks do: {', '.join(result.matched)}"
            )
        else:
            label = "MISSING*" if result.required else "MISSING "
            lines.append(f"{label} {result.key}  no strategy matched")
    failed = [r for r in results if r.failed]
    drifted = [r for r in results if r.status == "degraded"]
    lines.append("")
    lines.append(
        f"{len(failed)} required element(s) missing, {len(drifted)} on fallback strategies "
        "(* = required)"
    )
    return "\n".join(lines)
