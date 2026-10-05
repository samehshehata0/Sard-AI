import pytest
from playwright.sync_api import sync_playwright

from app.automation.canary import format_report, run_canary
from app.automation.notebooklm_ui import (
    NEW_NOTEBOOK_BUTTON,
    NOTEBOOK_EDITOR,
    SLIDE_DECK_BUTTON,
    build_registry,
)


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


def by_key(results):
    return {r.key: r for r in results}


def test_primary_strategy_match_is_ok(page):
    page.set_content('<button class="create-new-button">+</button>')
    result = by_key(run_canary(page, build_registry(), {"home"}))[NEW_NOTEBOOK_BUTTON]
    assert result.status == "ok"
    assert result.matched[0] == "structure-1"
    assert not result.failed


def test_fallback_only_match_is_reported_as_drift(page):
    page.set_content("<button>Create notebook</button>")
    result = by_key(run_canary(page, build_registry(), {"home"}))[NEW_NOTEBOOK_BUTTON]
    assert result.status == "degraded"
    assert result.matched == ("text-9",)
    assert "DRIFT" in format_report([result])


def test_missing_required_element_fails_and_is_starred(page):
    page.set_content("<p>nothing here</p>")
    result = by_key(run_canary(page, build_registry(), {"home"}))[NEW_NOTEBOOK_BUTTON]
    assert result.status == "missing"
    assert result.failed is True
    assert "MISSING*" in format_report([result])


def test_missing_optional_element_does_not_fail(page):
    page.set_content("<p>nothing here</p>")
    welcome = by_key(run_canary(page, build_registry(), {"home"}))["home.welcome_page"]
    assert welcome.status == "missing"
    assert welcome.failed is False


def test_elements_on_other_screens_are_skipped_not_clicked(page):
    page.set_content("<p>nothing here</p>")
    results = by_key(run_canary(page, build_registry(), {"home"}))
    assert results[SLIDE_DECK_BUTTON].status == "skipped"
    assert results["slide_deck.generate_now"].status == "skipped"


def test_notebook_screen_checks_in_notebook_elements(page):
    page.set_content(
        '<div class="notebook-editor"><p>x</p></div>'
        '<basic-create-artifact-button aria-label="مجموعة الشرايح">Slides</basic-create-artifact-button>'
    )
    results = by_key(run_canary(page, build_registry(), {"notebook"}))
    assert results[NOTEBOOK_EDITOR].status == "ok"
    assert results[SLIDE_DECK_BUTTON].status == "ok"
    assert results[NEW_NOTEBOOK_BUTTON].status == "skipped"
