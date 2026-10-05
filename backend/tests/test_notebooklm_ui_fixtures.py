import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.automation.notebooklm_ui import build_registry
from app.automation.slide_deck import GENERATE_NOW


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "notebooklm_ui"
SERVICE = Path(__file__).resolve().parents[1] / "app" / "services" / "notebooklm_service.py"

# Covered by the richer dialog fixture in test_slide_deck_dialog.py.
COVERED_ELSEWHERE = {GENERATE_NOW}


def parse_header(html: str) -> dict[str, str]:
    header = re.search(r"<!--\s*(expect:.*?)\s*-->", html).group(1)
    fields: dict[str, str] = {}
    for part in header.split(";"):
        name, _, value = part.strip().partition(":")
        fields[name.strip()] = value.strip()
    return fields


def fixture_files() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.html"))


def key_of(path: Path) -> str:
    stem = path.name[: -len(".html")]
    registry_keys = build_registry().keys()
    return next(key for key in registry_keys if stem == key or stem.startswith(key + "."))


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_resolves_through_the_expected_strategy(page, path):
    registry = build_registry()
    key = key_of(path)
    html = path.read_text(encoding="utf-8")
    header = parse_header(html)
    page.set_content(html)

    params = {"text": json.dumps(header["text"], ensure_ascii=False)} if "text" in header else None

    if "hidden" in header:
        # Hidden elements such as file inputs only need to exist.
        matched = [
            strategy.name
            for strategy, locator in registry.candidates(page, key)
            if locator.count() > 0
        ]
        assert matched and matched[0] == header["expect"]
        return

    scope = page
    if "scope" in header:
        scope = registry.resolve(page, header["scope"], timeout_ms=500).locator
    if "scope-css" in header:
        scope = page.locator(header["scope-css"]).first

    resolved = registry.find(scope, key, params)
    assert resolved is not None, f"{key} did not match {path.name}"
    assert resolved.strategy == header["expect"]


def test_every_registered_element_has_a_fixture():
    covered = {key_of(path) for path in fixture_files()} | COVERED_ELSEWHERE
    missing = set(build_registry().keys()) - covered
    assert not missing, f"Registered elements without a fixture: {sorted(missing)}"


def test_every_fixture_belongs_to_a_registered_element():
    for path in fixture_files():
        assert key_of(path) in build_registry().keys()


def test_every_element_has_a_known_screen_and_unique_strategy_names():
    registry = build_registry()
    for key in registry.keys():
        names = [s.name for s in registry.strategies(key)]
        assert len(names) == len(set(names)), key
        assert registry.element(key).screen


def test_service_spells_no_selectors_of_its_own():
    source = SERVICE.read_text(encoding="utf-8")
    forbidden = ["has-text", "get_by_text", "inner_text", "outerHTML", "page.locator(", "xpath="]
    assert [token for token in forbidden if token in source] == []
    assert not re.search(r"\.locator\(\s*[\"']", source), "raw selector string passed to .locator()"
