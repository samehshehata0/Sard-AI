import os

import pytest

from app.automation.errors import NeedsLoginError, PermanentStepError, TransientStepError
from app.services import notebooklm_service
from app.services.notebooklm_service import NotebookLMService

from tests.test_automation_steps import FakePage


class FakePageWithGoto(FakePage):
    def goto(self, url, **kwargs):
        self.visited = url


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
def pipeline(tmp_path, monkeypatch):
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
    source = tmp_path / "story.md"
    source.write_text("# Title\nbody", encoding="utf-8")
    return service, page, browser, calls, str(source), str(tmp_path / "work")


def test_pipeline_runs_every_step_in_order_and_returns_the_deck(pipeline):
    service, page, browser, calls, source, target = pipeline
    assert service._sync_pipeline(source, "prompt", target) == "deck.pdf"
    assert calls == ["create_notebook", "dismiss", "upload", "indexing", "request", "download"]
    assert browser.closed is True


def test_failing_step_is_typed_names_the_step_and_saves_evidence(pipeline):
    service, page, browser, calls, source, target = pipeline

    def broken(p, prompt):
        raise RuntimeError("button vanished")

    service._request_slide_deck = broken
    with pytest.raises(TransientStepError) as excinfo:
        service._sync_pipeline(source, "prompt", target)
    assert excinfo.value.evidence_dir == os.path.join(target, "notebooklm_artifacts", "request_slide_deck")
    assert "download" not in calls
    assert browser.closed is True


def test_expired_login_on_arrival_is_needs_login_with_evidence(pipeline):
    service, page, browser, calls, source, target = pipeline
    page.url = "https://accounts.google.com/signin"
    with pytest.raises(NeedsLoginError) as excinfo:
        service._sync_pipeline(source, "prompt", target)
    assert calls == []
    assert excinfo.value.evidence_dir == os.path.join(target, "notebooklm_artifacts", "pipeline")


def test_empty_source_is_permanent_and_never_opens_a_browser(pipeline):
    service, page, browser, calls, source, target = pipeline
    open(source, "w", encoding="utf-8").write("   ")
    with pytest.raises(PermanentStepError):
        service._sync_pipeline(source, "prompt", target)
    assert calls == []
