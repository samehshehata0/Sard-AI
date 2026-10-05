from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.automation.locators import LocatorNotFoundError, LocatorValidationError
from app.automation.slide_deck import (
    GENERATE_NOW,
    GenerateNowError,
    GenerateNowLayoutError,
    build_registry,
    click_generate_now,
)


FIXTURE = (Path(__file__).parent / "fixtures" / "slide_deck_dialog.html").read_text(encoding="utf-8")


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


def load(page, html=FIXTURE):
    page.set_content(html)


def test_generate_now_resolves_via_relative_xpath_and_never_the_later_button(page):
    load(page)
    resolved = build_registry().resolve(page, GENERATE_NOW, timeout_ms=2000)
    assert resolved.strategy == "relative-xpath"
    assert resolved.locator.get_attribute("id") == "now"


def test_click_generate_now_clicks_only_generate_now_and_confirms_start(page):
    load(page)
    strategy = click_generate_now(page, build_registry(), find_timeout_ms=2000, started_timeout_ms=2000)
    assert strategy == "relative-xpath"
    assert page.evaluate("window.clicked") == ["now"]


def test_role_strategy_is_used_when_custom_element_anchor_is_gone(page):
    # NotebookLM renames nb-button: the XPath tiers fail, the structural tier still works.
    load(page, FIXTURE.replace("nb-button", "nb-btn"))
    resolved = build_registry().resolve(page, GENERATE_NOW, timeout_ms=2000)
    assert resolved.strategy == "role-last-action"
    assert resolved.locator.get_attribute("id") == "now"


def test_text_strategy_excludes_generate_later(page):
    registry = build_registry()
    text_selector = next(s.selector for s in registry.strategies(GENERATE_NOW) if s.name == "text")
    load(page)
    matches = page.locator(text_selector)
    assert matches.count() == 1
    assert matches.first.get_attribute("id") == "now"


def test_single_action_dialog_fails_loudly_without_clicking(page):
    load(page, FIXTURE.replace(
        '<span><nb-button><button id="later" aria-label="later">Generate later</button></nb-button></span>', ""
    ))
    with pytest.raises(GenerateNowLayoutError) as excinfo:
        click_generate_now(page, build_registry(), find_timeout_ms=1000)
    assert excinfo.value.retryable is False
    assert "layout" in str(excinfo.value)
    assert page.evaluate("window.clicked") == []


def test_last_action_labelled_later_is_refused_even_if_it_is_last(page):
    # Order flipped by NotebookLM: Generate now first, Generate later last.
    flipped = FIXTURE.replace(">Generate later<", ">TMP<").replace(">Generate<", ">Generate later<").replace(">TMP<", ">Generate<")
    flipped = flipped.replace('id="later"', 'id="tmp"').replace('id="now"', 'id="later"').replace('id="tmp"', 'id="now"')
    # Now the DOM is: [id=now "Generate"], [id=later "Generate later"]; later is last.
    load(page, flipped)
    with pytest.raises(GenerateNowLayoutError) as excinfo:
        click_generate_now(page, build_registry(), find_timeout_ms=1000)
    assert "later" in str(excinfo.value).lower()
    assert page.evaluate("window.clicked") == []


def test_missing_dialog_raises_not_found(page):
    load(page, "<html><body></body></html>")
    with pytest.raises(LocatorNotFoundError):
        build_registry().resolve(page, GENERATE_NOW, timeout_ms=500)


def test_dialog_closing_without_generating_state_is_an_error(page):
    html = FIXTURE.replace("card.textContent = 'Creating slide deck';", "card.textContent = 'ok';")
    load(page, html)
    with pytest.raises(GenerateNowError) as excinfo:
        click_generate_now(page, build_registry(), find_timeout_ms=1000, started_timeout_ms=1000)
    assert excinfo.value.retryable is True
    assert "generating" in str(excinfo.value)
