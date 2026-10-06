import pytest

from save_auth import prefer_headless


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_macos_and_windows_get_a_visible_browser_even_though_they_never_set_display(platform):
    assert prefer_headless({}, platform) is False


def test_linux_without_a_display_has_no_window_to_open():
    assert prefer_headless({}, "linux") is True


@pytest.mark.parametrize("env", [{"DISPLAY": ":0"}, {"WAYLAND_DISPLAY": "wayland-0"}])
def test_linux_with_a_display_gets_a_visible_browser(env):
    assert prefer_headless(env, "linux") is False


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_headless_can_always_be_asked_for(platform, value):
    assert prefer_headless({"NOTEBOOKLM_HEADLESS": value, "DISPLAY": ":0"}, platform) is True


def test_other_values_do_not_force_headless():
    assert prefer_headless({"NOTEBOOKLM_HEADLESS": "false"}, "darwin") is False
