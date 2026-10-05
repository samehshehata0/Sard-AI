import random
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.automation.pacing import HumanPacer
from app.automation.slide_deck import build_registry, click_generate_now
from app.services.notebooklm_service import NotebookLMService

from tests.test_automation_steps import FakePage


APP = Path(__file__).resolve().parents[1]


class FakeMouse:
    def __init__(self):
        self.moves = []

    def move(self, x, y, steps=1):
        self.moves.append((x, y, steps))


class FakeKeyboard:
    def __init__(self):
        self.inserted = []

    def insert_text(self, text):
        self.inserted.append(text)


class FakeTarget:
    def __init__(self, box=None):
        self.box = box
        self.events = []

    def scroll_into_view_if_needed(self, timeout=None):
        self.events.append("scroll")

    def bounding_box(self):
        return self.box

    def click(self, force=False, position=None):
        self.events.append(("click", force, position))

    def fill(self, text):
        self.events.append(("fill", text))


class PacedPage(FakePage):
    def __init__(self):
        super().__init__()
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.pauses = []

    def wait_for_timeout(self, ms):
        self.pauses.append(ms)
        super().wait_for_timeout(ms)


def pacer(enabled=True, **kwargs):
    return HumanPacer(enabled=enabled, rng=random.Random(7), **kwargs)


def test_disabled_pacer_does_the_plain_instant_thing():
    page, target = PacedPage(), FakeTarget(box={"x": 0, "y": 0, "width": 100, "height": 40})
    p = pacer(enabled=False)
    p.pause(page)
    p.click(page, target)
    p.type_text(page, target, "x" * 1000)
    assert page.pauses == []
    assert page.mouse.moves == []
    assert target.events == [("click", True, None), ("fill", "x" * 1000)]


def test_pauses_stay_inside_the_configured_range():
    page = PacedPage()
    p = pacer(min_ms=400, max_ms=1500)
    for _ in range(100):
        p.pause(page)
    assert min(page.pauses) >= 400 and max(page.pauses) <= 1500
    assert len(set(page.pauses)) > 20  # actually random


def test_reversed_range_is_corrected():
    p = pacer(min_ms=900, max_ms=300)
    assert (p.min_ms, p.max_ms) == (300, 900)


def test_click_moves_the_mouse_onto_the_element_then_clicks_there():
    page, target = PacedPage(), FakeTarget(box={"x": 100, "y": 200, "width": 80, "height": 40})
    pacer().click(page, target)
    (x, y, steps), = page.mouse.moves
    assert 100 + 80 * 0.3 <= x <= 100 + 80 * 0.7
    assert 200 + 40 * 0.3 <= y <= 200 + 40 * 0.7
    assert 8 <= steps <= 20
    kind, force, position = target.events[-1]
    assert (kind, force) == ("click", True)
    assert 24 <= position["x"] <= 56 and 12 <= position["y"] <= 28
    assert len(page.pauses) >= 2  # before moving and before clicking


def test_click_without_a_bounding_box_falls_back_to_a_plain_click():
    page, target = PacedPage(), FakeTarget(box=None)
    pacer().click(page, target)
    assert page.mouse.moves == []
    assert target.events[-1] == ("click", True, None)


def test_long_text_is_entered_in_pieces_that_add_up_to_the_original():
    page, target = PacedPage(), FakeTarget(box={"x": 0, "y": 0, "width": 200, "height": 60})
    text = "قصة تعليمية عن الشمس " * 120
    pacer().type_text(page, target, text)
    assert ("fill", "") in target.events
    assert "".join(page.keyboard.inserted) == text
    assert len(page.keyboard.inserted) > 5
    assert all(len(chunk) <= 240 for chunk in page.keyboard.inserted)


def test_short_text_is_a_plain_fill():
    page, target = PacedPage(), FakeTarget()
    pacer().type_text(page, target, "short prompt")
    assert target.events == [("fill", "short prompt")]
    assert page.keyboard.inserted == []


def test_pacing_added_to_a_long_prompt_is_small_next_to_generation_time():
    page, target = PacedPage(), FakeTarget(box={"x": 0, "y": 0, "width": 200, "height": 60})
    pacer().type_text(page, target, "ب" * 3000)
    assert sum(page.pauses) < 15_000


def test_pacer_reads_its_settings():
    class S:
        NOTEBOOKLM_HUMAN_PACING = False
        NOTEBOOKLM_PACING_MIN_MS = 10
        NOTEBOOKLM_PACING_MAX_MS = 20

    p = HumanPacer.from_settings(S)
    assert (p.enabled, p.min_ms, p.max_ms) == (False, 10, 20)


def test_tests_run_with_pacing_off_by_default():
    assert NotebookLMService().pacer.enabled is False


def test_no_fixed_sleeps_left_in_the_flow():
    for relative in ("app/services/notebooklm_service.py", "app/automation/slide_deck.py", "notebooklm_canary.py"):
        source = (APP / relative).read_text(encoding="utf-8")
        assert not re.search(r"wait_for_timeout\(\s*\d", source), relative
    service = (APP / "app/services/notebooklm_service.py").read_text(encoding="utf-8")
    # The one remaining sleep is the poll interval of the download wait loop.
    assert re.findall(r"wait_for_timeout\((.*?)\)", service) == ["poll_ms"]


# --- real browser ---------------------------------------------------------


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


def fast_pacer():
    return HumanPacer(enabled=True, min_ms=1, max_ms=3, rng=random.Random(3))


def test_chunked_entry_puts_arabic_text_into_a_real_textarea(page):
    page.set_content('<textarea id="t" rows="5" cols="40"></textarea>')
    text = "اكتب قصة تعليمية عن دورة الماء في الطبيعة. " * 25
    fast_pacer().type_text(page, page.locator("#t"), text)
    assert page.locator("#t").input_value() == text


def test_chunked_entry_works_in_a_contenteditable_field(page):
    page.set_content('<div id="c" contenteditable="true" style="width:300px;height:80px"></div>')
    text = "Write a story about the water cycle. " * 20
    fast_pacer().type_text(page, page.locator("#c"), text)
    assert page.locator("#c").inner_text().strip() == text.strip()


def test_paced_click_really_clicks_the_element(page):
    page.set_content(
        '<button id="b" style="margin:60px;width:120px;height:40px" '
        "onclick=\"window.n=(window.n||0)+1\">go</button>"
    )
    fast_pacer().click(page, page.locator("#b"))
    assert page.evaluate("window.n") == 1


def test_generate_now_works_with_the_pacer_on(page):
    html = (Path(__file__).parent / "fixtures" / "slide_deck_dialog.html").read_text(encoding="utf-8")
    page.set_content(html)
    click_generate_now(
        page, build_registry(), find_timeout_ms=2000, started_timeout_ms=2000, pacer=fast_pacer()
    )
    assert page.evaluate("window.clicked") == ["now"]


# --- readiness wait -------------------------------------------------------


class Control:
    def __init__(self, states):
        self.states = iter(states)
        self.current = False

    @property
    def locator(self):
        return self

    def is_enabled(self):
        self.current = next(self.states, self.current)
        return self.current

    def get_attribute(self, name):
        return None


def service_with(control, monkeypatch):
    service = NotebookLMService()
    monkeypatch.setattr(service.registry, "find", lambda scope, key, params=None: control)
    return service


def test_ready_wait_needs_the_control_to_stay_enabled(monkeypatch):
    page = FakePage()
    # Enabled, flips off once, then enabled for good: the flip resets the clock.
    service = service_with(Control([True, True, False] + [True] * 50), monkeypatch)
    service._wait_until_ready_to_generate(page)
    # Flips off at 1s, holds again from 1.5s, so ready only at 1.5s + 3s.
    assert page.waited_ms == 4500


def test_ready_wait_gives_up_quietly_after_a_minute(monkeypatch, caplog):
    page = FakePage()
    service = service_with(Control([False] * 500), monkeypatch)
    with caplog.at_level("WARNING"):
        service._wait_until_ready_to_generate(page)
    assert page.waited_ms >= 60_000
    assert "did not settle" in caplog.text


# --- the slide deck request, end to end in a real browser ------------------

FLOW = (Path(__file__).parent / "fixtures" / "notebooklm_flow.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("paced", [False, True], ids=["pacing-off", "pacing-on"])
def test_request_slide_deck_end_to_end_on_a_fake_notebook_page(page, monkeypatch, paced):
    from app.core.config import settings

    monkeypatch.setattr(settings, "NOTEBOOKLM_READY_STABLE_SECONDS", 0.5)
    page.set_content(FLOW)
    service = NotebookLMService()
    if paced:
        service.pacer = fast_pacer()
    prompt = "أنشئ عرضًا تعليميًا عن دورة الماء مع شرائح بسيطة. " * 20

    service._request_slide_deck(page, prompt)

    assert page.evaluate("window.clicked") == ["now"]
    assert page.evaluate("window.submitted") == prompt
