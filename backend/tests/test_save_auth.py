import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import save_auth
from app.core.config import settings
from app.services.notebooklm_service import NotebookLMService
from save_auth import capture_session, chrome_command, find_chrome, signed_in

ROOT = Path(__file__).resolve().parents[2]


# --- finding Chrome -----------------------------------------------------------------------------


def test_chrome_is_found_in_its_usual_place_on_macos():
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert find_chrome({}, "darwin", exists=lambda path: path == mac) == mac
    assert find_chrome({}, "darwin", exists=lambda path: False) is None


def test_chrome_is_found_under_program_files_on_windows():
    env = {"PROGRAMFILES": r"C:\Program Files"}
    expected = r"C:\Program Files/Google/Chrome/Application/chrome.exe".replace("/", __import__("os").sep)
    assert find_chrome(env, "win32", exists=lambda path: path == expected) == expected


def test_chrome_is_found_on_the_path_on_linux_trying_the_usual_names_in_order():
    available = {"chromium": "/usr/bin/chromium"}
    assert find_chrome({}, "linux", which=lambda name: available.get(name)) == "/usr/bin/chromium"
    assert find_chrome({}, "linux", which=lambda name: None) is None


def test_an_explicit_chrome_path_wins_and_is_not_second_guessed():
    env = {"NOTEBOOKLM_CHROME_PATH": "/opt/my-chrome"}
    assert find_chrome(env, "darwin", exists=lambda path: path == "/opt/my-chrome") == "/opt/my-chrome"
    assert find_chrome(env, "darwin", exists=lambda path: False) is None  # a wrong override is not silently replaced


# --- how Chrome is started ----------------------------------------------------------------------


def test_chrome_is_started_like_a_person_would_with_only_a_debug_port_and_its_own_profile():
    command = chrome_command("/chrome", "/profiles/sard", 9333, "https://notebooklm.google.com")
    assert command[0] == "/chrome" and command[-1] == "https://notebooklm.google.com"
    assert "--remote-debugging-port=9333" in command
    assert "--user-data-dir=/profiles/sard" in command
    # Nothing that disguises the browser or marks it as automated.
    forbidden = ("--enable-automation", "--disable-blink-features", "--user-agent", "--headless", "--no-sandbox")
    assert not [arg for arg in command if arg.startswith(forbidden)]


# --- noticing that a person has signed in ---------------------------------------------------------


class FakePage:
    def __init__(self, url):
        self.url = url


class FakeContext:
    def __init__(self, cookies=(), urls=()):
        self._cookies = [{"name": name} for name in cookies]
        self.pages = [FakePage(url) for url in urls]

    def cookies(self):
        return self._cookies


NOTEBOOKLM = "https://notebooklm.google.com/"


@pytest.mark.parametrize("cookie", ["SID", "__Secure-1PSID", "__Secure-3PSID"])
def test_signed_in_means_a_google_session_and_notebooklm_open(cookie):
    assert signed_in(FakeContext([cookie, "NID"], [NOTEBOOKLM])) is True


def test_notebooklm_alone_does_not_count_because_signed_out_visitors_see_a_landing_page():
    assert signed_in(FakeContext(["NID"], [NOTEBOOKLM])) is False


def test_a_google_session_alone_does_not_count_until_notebooklm_is_open():
    assert signed_in(FakeContext(["SID"], ["https://accounts.google.com/signin"])) is False
    assert signed_in(FakeContext(["SID"], [])) is False


def test_a_lookalike_host_does_not_count():
    assert signed_in(FakeContext(["SID"], ["https://notebooklm.google.com.evil.example/"])) is False


# --- no automatic login anywhere ------------------------------------------------------------------


def test_the_worker_never_tries_to_sign_in_by_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_STORAGE_STATE_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(save_auth.os, "getcwd", lambda: str(tmp_path))
    service = NotebookLMService()
    monkeypatch.setattr("app.services.notebooklm_service.storage_state_candidates", lambda: [str(tmp_path / "missing.json")])
    assert service._storage_state_path() is None  # so the job is parked as needs_login, with no login attempt


def test_no_password_is_read_or_stored_for_google():
    assert not hasattr(settings, "NOTEBOOKLM_EMAIL") and not hasattr(settings, "NOTEBOOKLM_PASSWORD")
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "NOTEBOOKLM_PASSWORD" not in text and "ensure_notebooklm_session" not in text, path.name
    assert not hasattr(save_auth, "_fill_input") and not hasattr(save_auth, "ensure_notebooklm_session")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "NOTEBOOKLM_PASSWORD" not in example and "NOTEBOOKLM_EMAIL" not in example


def test_the_chrome_profile_holding_the_login_lives_in_the_home_folder_not_the_project():
    profile = Path(save_auth.default_profile_dir({}))
    assert profile == Path.home() / ".sard-ai" / "chrome-profile"
    assert ROOT not in profile.parents  # never inside the repository, so never committed or mounted into Docker
    assert save_auth.default_profile_dir({"NOTEBOOKLM_CHROME_PROFILE": "/elsewhere"}) == "/elsewhere"
    assert "storage_state.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# --- the real thing, with a real Chrome and a local page standing in for Google -----------------------

needs_chrome = pytest.mark.skipif(find_chrome() is None, reason="Google Chrome is not installed")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def local_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if self.path.startswith("/signed-in"):
                self.send_header("Set-Cookie", "SID=signed-in-user; Path=/")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>notebooks</h1></body></html>")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def port_is_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def signed_in_on_local_site(context) -> bool:
    return any(c["name"] == "SID" for c in context.cookies()) and any("/signed-in" in p.url for p in context.pages)


@needs_chrome
def test_a_session_is_saved_once_the_user_has_signed_in_and_chrome_is_closed_afterwards(tmp_path, local_site):
    port = free_port()
    destination = tmp_path / "auth" / "storage_state.json"
    messages = []

    saved = capture_session(
        str(destination),
        port=port,
        profile_dir=str(tmp_path / "profile"),
        start_url=f"{local_site}/signed-in",
        ready=signed_in_on_local_site,
        extra_args=("--headless=new",),  # no window in the test run
        timeout=60,
        say=messages.append,
    )

    state = json.loads(Path(saved).read_text(encoding="utf-8"))
    assert any(cookie["name"] == "SID" and cookie["value"] == "signed-in-user" for cookie in state["cookies"])
    assert (tmp_path / "profile").is_dir()  # Chrome used the profile folder it was given
    assert not port_is_open(port)  # the Chrome it opened is closed again
    assert any("Sign in to Google" in line for line in messages)  # the user is told what to do
    assert any("never types" in line for line in messages)


@needs_chrome
def test_it_gives_up_with_a_clear_message_and_closes_chrome_if_nobody_signs_in(tmp_path, local_site):
    port = free_port()
    with pytest.raises(RuntimeError, match="Timed out waiting for the sign-in"):
        capture_session(
            str(tmp_path / "state.json"),
            port=port,
            profile_dir=str(tmp_path / "profile"),
            start_url=f"{local_site}/not-signed-in",
            ready=signed_in_on_local_site,
            extra_args=("--headless=new",),
            timeout=4,
            say=lambda line: None,
        )
    assert not port_is_open(port)
    assert not (tmp_path / "state.json").exists()  # nothing half-saved


def test_it_explains_what_to_do_when_chrome_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(save_auth, "find_chrome", lambda: None)
    with pytest.raises(RuntimeError, match="NOTEBOOKLM_CHROME_PATH"):
        capture_session(str(tmp_path / "state.json"), port=free_port(), say=lambda line: None)
