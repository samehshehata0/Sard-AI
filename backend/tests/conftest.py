import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))



import pytest


@pytest.fixture(autouse=True)
def no_human_pacing(monkeypatch):
    """Tests never add human-like pauses; the pacer itself is tested directly."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "NOTEBOOKLM_HUMAN_PACING", False)
