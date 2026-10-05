"""Check NotebookLM's live UI against the locator registry.

Opens NotebookLM with the saved login, reports which locator strategy matches
for each element it can see without clicking, and exits non-zero if a required
element is missing. Run it before UI drift breaks a real generation:

    cd backend && python notebooklm_canary.py [--notebook-url URL] [--headed]

Exit codes: 0 all required elements found, 1 a required element is missing,
2 the NotebookLM login has expired (run `npm run auth`).
"""
import argparse
import sys

from playwright.sync_api import sync_playwright

from app.automation.canary import format_report, run_canary
from app.automation.errors import NeedsLoginError
from app.automation.notebooklm_ui import build_registry, page_has_landed
from app.automation.steps import check_session, wait_until
from app.core.config import settings
from app.services.notebooklm_service import NotebookLMService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--notebook-url", help="An existing notebook to check the in-notebook elements on")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()

    storage_path = NotebookLMService()._storage_state_path()
    if not storage_path:
        print("NotebookLM login is missing; run `npm run auth`.")
        return 2

    registry = build_registry()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        try:
            context = browser.new_context(storage_state=storage_path, viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(settings.NOTEBOOKLM_URL, wait_until="domcontentloaded", timeout=45000)
            wait_until(page, lambda: page_has_landed(page, registry), timeout_ms=15_000)
            try:
                check_session(page)
            except NeedsLoginError:
                print("NotebookLM login has expired; run `npm run auth`.")
                return 2
            results += run_canary(page, registry, {"home"})

            if args.notebook_url:
                page.goto(args.notebook_url, wait_until="domcontentloaded", timeout=45000)
                wait_until(page, lambda: page_has_landed(page, registry), timeout_ms=15_000)
                results += [r for r in run_canary(page, registry, {"notebook"}) if r.status != "skipped"]
        finally:
            browser.close()

    # One row per element: a result from a screen we reached beats a "skipped" row.
    merged = {}
    for result in results:
        if result.key not in merged or merged[result.key].status == "skipped":
            merged[result.key] = result
    unique = list(merged.values())
    print(format_report(unique))
    return 1 if any(r.failed for r in unique) else 0


if __name__ == "__main__":
    sys.exit(main())
