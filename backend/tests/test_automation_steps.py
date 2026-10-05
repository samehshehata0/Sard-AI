import os

import pytest

from app.automation.errors import (
    NeedsLoginError,
    NotebookLMGenerationError,
    PermanentStepError,
    QuotaExhaustedError,
    TransientStepError,
)
from app.automation.steps import check_session, run_step, wait_until


class FakeLocator:
    def __init__(self, visible: bool):
        self._visible = visible

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._visible else 0

    def is_visible(self):
        return self._visible


class FakePage:
    """Just enough of a Playwright page to run steps without a browser."""

    def __init__(self, url="https://notebooklm.google.com/notebook/abc", visible_texts=(), screenshot_fails=False):
        self.url = url
        self.visible_texts = set(visible_texts)
        self.screenshot_fails = screenshot_fails
        self.waited_ms = 0

    def locator(self, selector):
        return FakeLocator(selector.removeprefix("text=") in self.visible_texts)

    def screenshot(self, path, full_page=False):
        if self.screenshot_fails:
            raise RuntimeError("screenshot failed")
        with open(path, "wb") as handle:
            handle.write(b"png")

    def content(self):
        return "<html>dom</html>"

    def wait_for_timeout(self, ms):
        self.waited_ms += ms


def test_step_runs_precondition_action_postcondition_in_order(tmp_path):
    calls = []
    result = run_step(
        FakePage(),
        "demo",
        lambda: calls.append("action") or "done",
        pre=lambda: calls.append("pre"),
        post=lambda: calls.append("post"),
        evidence_dir=str(tmp_path),
    )
    assert result == "done"
    assert calls == ["pre", "action", "post"]
    assert os.listdir(tmp_path) == []


def test_failed_precondition_stops_before_the_action_and_is_transient(tmp_path):
    calls = []
    with pytest.raises(TransientStepError) as excinfo:
        run_step(
            FakePage(),
            "demo",
            lambda: calls.append("action"),
            pre=lambda: False,
            evidence_dir=str(tmp_path),
        )
    assert calls == []
    assert "precondition" in str(excinfo.value)
    assert excinfo.value.retryable is True


def test_failed_postcondition_is_an_error_even_though_the_action_ran(tmp_path):
    with pytest.raises(TransientStepError) as excinfo:
        run_step(FakePage(), "demo", lambda: "x", post=lambda: False, evidence_dir=str(tmp_path))
    assert "postcondition" in str(excinfo.value)


def test_condition_that_raises_counts_as_not_holding(tmp_path):
    def boom():
        raise RuntimeError("element detached")

    with pytest.raises(TransientStepError) as excinfo:
        run_step(FakePage(), "demo", lambda: "x", post=boom, evidence_dir=str(tmp_path))
    assert "could not be checked" in str(excinfo.value)


def test_unexpected_exception_becomes_transient_with_cause_and_evidence(tmp_path):
    def action():
        raise ValueError("selector miss")

    with pytest.raises(TransientStepError) as excinfo:
        run_step(FakePage(), "request_slide_deck", action, evidence_dir=str(tmp_path))
    error = excinfo.value
    assert isinstance(error.__cause__, ValueError)
    assert error.retryable is True
    assert error.evidence_dir == os.path.join(str(tmp_path), "request_slide_deck")
    assert sorted(os.listdir(error.evidence_dir)) == ["error.txt", "page.html", "screenshot.png"]
    assert "selector miss" in open(os.path.join(error.evidence_dir, "error.txt"), encoding="utf-8").read()


def test_typed_error_passes_through_unchanged_and_is_not_retryable(tmp_path):
    original = PermanentStepError("unexpected layout")

    def action():
        raise original

    with pytest.raises(PermanentStepError) as excinfo:
        run_step(FakePage(), "demo", action, evidence_dir=str(tmp_path))
    assert excinfo.value is original
    assert original.retryable is False
    assert original.evidence_dir is not None


def test_error_that_already_has_evidence_is_not_captured_twice(tmp_path):
    original = TransientStepError("inner")
    original.evidence_dir = "already-saved"

    def action():
        raise original

    with pytest.raises(TransientStepError):
        run_step(FakePage(), "outer", action, evidence_dir=str(tmp_path))
    assert original.evidence_dir == "already-saved"
    assert os.listdir(tmp_path) == []


def test_no_evidence_dir_means_nothing_is_written():
    with pytest.raises(TransientStepError) as excinfo:
        run_step(FakePage(), "demo", lambda: 1 / 0)
    assert excinfo.value.evidence_dir is None


def test_evidence_failure_never_hides_the_real_error(tmp_path):
    with pytest.raises(TransientStepError) as excinfo:
        run_step(FakePage(screenshot_fails=True), "demo", lambda: 1 / 0, evidence_dir=str(tmp_path))
    assert "division by zero" in str(excinfo.value)
    assert "error.txt" in os.listdir(excinfo.value.evidence_dir)


@pytest.mark.parametrize("url", ["https://accounts.google.com/v3/signin", "https://notebooklm.google.com/signin"])
def test_login_page_raises_needs_login_before_any_work(url, tmp_path):
    calls = []
    with pytest.raises(NeedsLoginError) as excinfo:
        run_step(FakePage(url=url), "demo", lambda: calls.append("action"), pre=lambda: calls.append("pre"), evidence_dir=str(tmp_path))
    assert calls == []
    assert excinfo.value.retryable is False


def test_login_expiring_during_the_action_is_caught_after_it():
    page = FakePage()

    def action():
        page.url = "https://accounts.google.com/signin"

    with pytest.raises(NeedsLoginError):
        run_step(page, "demo", action)


def test_quota_refusal_shown_after_the_action_raises_quota_exhausted(tmp_path):
    page = FakePage()

    def action():
        page.visible_texts.add("Daily limit reached")

    with pytest.raises(QuotaExhaustedError) as excinfo:
        run_step(page, "request_slide_deck", action, quota_markers=("Daily limit reached",), evidence_dir=str(tmp_path))
    assert excinfo.value.retryable is False
    assert excinfo.value.evidence_dir is not None


def test_quota_detection_is_off_without_markers():
    page = FakePage(visible_texts={"Daily limit reached"})
    check_session(page)


def test_every_error_kind_is_a_generation_error_with_the_arabic_message():
    for kind in (TransientStepError, PermanentStepError, NeedsLoginError, QuotaExhaustedError):
        assert issubclass(kind, NotebookLMGenerationError)
        assert kind("x").user_message == NotebookLMGenerationError.user_message
    assert NotebookLMGenerationError("x").retryable is None


def test_wait_until_polls_until_the_condition_holds():
    page = FakePage()
    checks = iter([False, False, True])
    assert wait_until(page, lambda: next(checks), timeout_ms=5000, interval_ms=250) is True
    assert page.waited_ms == 500


def test_wait_until_gives_up_at_the_timeout():
    page = FakePage()
    assert wait_until(page, lambda: False, timeout_ms=1000, interval_ms=250) is False
    assert page.waited_ms == 1000


def test_wait_until_stable_needs_the_condition_to_hold_continuously():
    from app.automation.steps import wait_until_stable

    page = FakePage()
    states = iter([True, True, False, True, True, True, True, True, True])
    assert wait_until_stable(page, lambda: next(states), stable_ms=1500, timeout_ms=20_000, interval_ms=500) is True
    # Two good polls, a flip (reset), then it must hold for 1500ms again.
    assert page.waited_ms == 3000


def test_wait_until_stable_gives_up_at_the_timeout():
    from app.automation.steps import wait_until_stable

    page = FakePage()
    assert wait_until_stable(page, lambda: False, stable_ms=1000, timeout_ms=3000, interval_ms=500) is False
    assert page.waited_ms == 3000
