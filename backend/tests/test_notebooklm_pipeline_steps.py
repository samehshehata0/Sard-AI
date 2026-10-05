import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.automation.errors import NeedsLoginError, PermanentStepError, TransientStepError
from app.automation.notebooklm_ui import (
    ARTIFACT_ITEM,
    GENERATING_INDICATOR,
    SOURCE_TITLE,
)
from app.services import notebooklm_service
from app.services.notebooklm_service import NotebookLMService

from tests.test_automation_steps import FakePage


NOTEBOOK = "https://notebooklm.google.com/notebook/abc123"
APP = Path(__file__).resolve().parents[1]


class FakePageWithGoto(FakePage):
    def __init__(self, url=NOTEBOOK):
        super().__init__(url=url)
        self.visited = []

    def goto(self, url, **kwargs):
        self.visited.append(url)


class FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_context(self, **kwargs):
        return FakeContext(self._page)

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = self
        self._browser = browser

    def launch(self, **kwargs):
        return self._browser

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def flow(tmp_path, monkeypatch):
    page = FakePageWithGoto()
    browser = FakeBrowser(page)
    monkeypatch.setattr(notebooklm_service, "sync_playwright", lambda: FakePlaywright(browser))
    service = NotebookLMService()
    calls = []
    monkeypatch.setattr(service, "_storage_state_path", lambda: "state.json")
    monkeypatch.setattr(service, "_page_has_notebook_editor", lambda p: True)
    monkeypatch.setattr(service, "_create_notebook", lambda p: calls.append("create_notebook"))
    monkeypatch.setattr(service, "_dismiss_onboarding_dialogs", lambda p: calls.append("dismiss"))
    monkeypatch.setattr(service, "_upload_source", lambda p, f, t: calls.append("upload"))
    monkeypatch.setattr(service, "_wait_for_source_indexing", lambda p, t: calls.append("indexing"))
    monkeypatch.setattr(service, "_request_slide_deck", lambda p, prompt: calls.append("request"))
    monkeypatch.setattr(service, "_download_artifact", lambda p, d: calls.append("download") or "deck.pdf")
    monkeypatch.setattr(service, "_delete_notebook", lambda p, url: calls.append("delete") or True)
    source = tmp_path / "story.md"
    source.write_text("# قصة الشمس\nbody", encoding="utf-8")
    return service, page, browser, calls, str(source), str(tmp_path / "work")


def nothing_found(monkeypatch, service, found=()):
    """Make the page look empty, except for the registry keys listed in `found`."""
    monkeypatch.setattr(
        service.registry, "find", lambda scope, key, params=None: object() if key in found else None
    )


# --- Submit -------------------------------------------------------------------------------


def test_submit_creates_the_notebook_adds_the_source_and_asks_for_the_deck(flow):
    service, page, browser, calls, source, target = flow
    assert service._sync_submit(source, "prompt", target) == NOTEBOOK
    assert calls == ["create_notebook", "dismiss", "upload", "indexing", "request"]  # and nothing is downloaded
    assert browser.closed is True


def test_submit_reports_the_notebook_url_as_soon_as_the_notebook_exists(flow):
    service, page, browser, calls, source, target = flow
    service._sync_submit(source, "prompt", target, on_notebook=lambda url: calls.append(f"saved {url}"))
    assert calls.index(f"saved {NOTEBOOK}") == calls.index("dismiss") + 1  # right after creating
    assert calls.index(f"saved {NOTEBOOK}") < calls.index("upload")  # before anything else can go wrong


def test_submit_carries_on_in_a_known_notebook_instead_of_creating_another(flow, monkeypatch):
    service, page, browser, calls, source, target = flow
    nothing_found(monkeypatch, service)  # source not added yet, deck not requested
    assert service._sync_submit(source, "prompt", target, notebook_url=NOTEBOOK) == NOTEBOOK
    assert page.visited == [NOTEBOOK]
    assert "create_notebook" not in calls
    assert calls == ["upload", "indexing", "request"]


def test_submit_skips_adding_the_source_when_it_is_already_in_the_notebook(flow, monkeypatch):
    service, page, browser, calls, source, target = flow
    nothing_found(monkeypatch, service, found={SOURCE_TITLE})
    service._sync_submit(source, "prompt", target, notebook_url=NOTEBOOK)
    assert calls == ["indexing", "request"]


@pytest.mark.parametrize("already", [GENERATING_INDICATOR, ARTIFACT_ITEM], ids=["generating", "finished"])
def test_submit_does_nothing_more_when_the_deck_was_already_requested(flow, monkeypatch, already):
    service, page, browser, calls, source, target = flow
    nothing_found(monkeypatch, service, found={already})
    assert service._sync_submit(source, "prompt", target, notebook_url=NOTEBOOK) == NOTEBOOK
    assert calls == []  # a second deck is never requested


def test_a_failing_submit_step_is_typed_names_the_step_and_saves_evidence(flow):
    service, page, browser, calls, source, target = flow

    def broken(p, prompt):
        raise RuntimeError("button vanished")

    service._request_slide_deck = broken
    with pytest.raises(TransientStepError) as excinfo:
        service._sync_submit(source, "prompt", target)
    assert excinfo.value.evidence_dir == os.path.join(target, "notebooklm_artifacts", "request_slide_deck")
    assert browser.closed is True


def test_expired_login_on_arrival_is_needs_login_with_evidence(flow):
    service, page, browser, calls, source, target = flow
    page.url = "https://accounts.google.com/signin"
    with pytest.raises(NeedsLoginError) as excinfo:
        service._sync_submit(source, "prompt", target)
    assert calls == []
    assert excinfo.value.evidence_dir == os.path.join(target, "notebooklm_artifacts", "pipeline")


def test_an_empty_source_is_permanent_and_never_opens_a_browser(flow):
    service, page, browser, calls, source, target = flow
    Path(source).write_text("   ", encoding="utf-8")
    with pytest.raises(PermanentStepError):
        service._sync_submit(source, "prompt", target)
    assert page.visited == []


# --- Collect ------------------------------------------------------------------------------


def test_collect_opens_the_notebook_downloads_the_deck_and_then_deletes_the_notebook(flow):
    service, page, browser, calls, source, target = flow
    assert service._sync_collect(NOTEBOOK, target) == ("deck.pdf", True)
    assert page.visited == [NOTEBOOK]
    assert calls == ["download", "delete"]  # the notebook is deleted only after the download
    assert "create_notebook" not in calls and "request" not in calls
    assert browser.closed is True


def test_a_failed_notebook_deletion_does_not_fail_collect(flow, monkeypatch):
    service, page, browser, calls, source, target = flow
    monkeypatch.setattr(service, "_delete_notebook", lambda p, url: False)
    assert service._sync_collect(NOTEBOOK, target) == ("deck.pdf", False)


def test_a_failed_download_is_typed_keeps_the_notebook_and_saves_evidence(flow):
    service, page, browser, calls, source, target = flow

    def broken(p, d):
        raise TransientStepError("did not finish")

    service._download_artifact = broken
    with pytest.raises(TransientStepError) as excinfo:
        service._sync_collect(NOTEBOOK, target)
    assert "delete" not in calls  # a notebook whose deck was not collected is left alone
    assert excinfo.value.evidence_dir == os.path.join(target, "notebooklm_artifacts", "collect")


def test_collect_on_an_expired_login_is_needs_login(flow):
    service, page, browser, calls, source, target = flow
    page.url = "https://accounts.google.com/signin"
    with pytest.raises(NeedsLoginError):
        service._sync_collect(NOTEBOOK, target)


# --- no more job file -----------------------------------------------------------------------


def test_nothing_is_written_to_a_notebooklm_job_file(flow):
    service, page, browser, calls, source, target = flow
    service._sync_submit(source, "prompt", target)
    service._sync_collect(NOTEBOOK, target)
    leftovers = [name for _, _, names in os.walk(target) for name in names if name == "notebooklm_job.json"]
    assert leftovers == []


def test_the_file_based_resume_state_is_gone_from_the_code():
    for path in (APP / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("notebooklm_job.json", "_resumable_notebook_url", "_save_job_state", "NOTEBOOKLM_RESUME_MAX_AGE_SECONDS"):
            assert token not in text, f"{token} still in {path.name}"


# --- deleting a notebook, in a real browser ----------------------------------------------------

HOME = """<!doctype html><html><body>
<welcome-page><p>Welcome</p></welcome-page>
<mat-card id="card"><a href="/notebook/abc123">قصة الشمس</a>
  <button aria-label="المزيد">more</button></mat-card>
<script>
  window.clicked = [];
  document.querySelector('button').addEventListener('click', () => {
    document.body.insertAdjacentHTML('beforeend', '<div role="menu"><div role="menuitem" id="del">حذف</div></div>');
    document.getElementById('del').addEventListener('click', () => {
      document.body.insertAdjacentHTML('beforeend', '<div role="dialog"><button id="ok">حذف</button></div>');
      document.getElementById('ok').addEventListener('click', () => {
        window.clicked.push('confirmed');
        document.getElementById('card').remove();
      });
    });
  });
</script></body></html>"""


@pytest.fixture(scope="module")
def browser_module():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def real_page(browser_module, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "NOTEBOOKLM_DELETE_TIMEOUT_MS", 400)
    page = browser_module.new_page()
    page.goto = lambda url, **kwargs: None  # the page under test is already "the home page"
    yield page
    page.close()


def test_delete_notebook_removes_the_notebook_from_the_home_page(real_page):
    real_page.set_content(HOME)
    assert NotebookLMService()._delete_notebook(real_page, NOTEBOOK) is True
    assert real_page.evaluate("window.clicked") == ["confirmed"]
    assert real_page.locator("#card").count() == 0


def test_delete_notebook_returns_false_instead_of_raising_when_the_notebook_is_not_there(real_page, caplog):
    real_page.set_content("<welcome-page><p>Welcome</p></welcome-page>")
    with caplog.at_level("WARNING"):
        assert NotebookLMService()._delete_notebook(real_page, NOTEBOOK) is False
    assert "Could not delete NotebookLM notebook" in caplog.text


def test_delete_notebook_returns_false_when_the_menu_has_no_delete(real_page):
    real_page.set_content(HOME.replace("حذف</div></div>');", "إعادة تسمية</div></div>');"))
    assert NotebookLMService()._delete_notebook(real_page, NOTEBOOK) is False
