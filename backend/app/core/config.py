import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(PROJECT_DIR / ".env", override=False)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)
    PROJECT_NAME: str = "Sard-AI Automation Service"
    API_V1_STR: str = ""
    
    # MongoDB Settings
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "sard_ai")
    
    # ImageKit Settings
    IMAGEKIT_PUBLIC_KEY: str = os.getenv("IMAGEKIT_PUBLIC_KEY", "")
    IMAGEKIT_PRIVATE_KEY: str = os.getenv("IMAGEKIT_PRIVATE_KEY", "")
    IMAGEKIT_URL_ENDPOINT: str = os.getenv("IMAGEKIT_URL_ENDPOINT", "")
    
    # Google Cloud TTS Credentials
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    
    # NotebookLM Settings
    NOTEBOOKLM_URL: str = os.getenv("NOTEBOOKLM_URL", "https://notebooklm.google.com")
    NOTEBOOKLM_EMAIL: str = os.getenv("NOTEBOOKLM_EMAIL", "")
    NOTEBOOKLM_PASSWORD: str = os.getenv("NOTEBOOKLM_PASSWORD", "")
    NOTEBOOKLM_STORAGE_STATE_PATH: str = os.getenv(
        "NOTEBOOKLM_STORAGE_STATE_PATH",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage_state.json"))
    )
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
    NOTEBOOKLM_TIMEOUT_SECONDS: int = int(os.getenv("NOTEBOOKLM_TIMEOUT_SECONDS", "1800"))
    NOTEBOOKLM_POLL_INTERVAL_SECONDS: float = float(
        os.getenv("NOTEBOOKLM_POLL_INTERVAL_SECONDS", "5")
    )
    NOTEBOOKLM_RESUME_MAX_AGE_SECONDS: int = int(
        os.getenv("NOTEBOOKLM_RESUME_MAX_AGE_SECONDS", "1800")
    )

    # Existing free Hugging Face / Edge TTS provider.
    HF_API_TOKEN: str = os.getenv("HF_API_TOKEN", "")
    HF_TTS_SPACE_URL: str = os.getenv(
        "HF_TTS_SPACE_URL",
        "https://innoai-edge-tts-text-to-speech.hf.space",
    )
    HF_TTS_ENDPOINT: str = os.getenv(
        "HF_TTS_ENDPOINT",
        "https://innoai-edge-tts-text-to-speech.hf.space/gradio_api/call/tts_interface",
    )
    HF_TTS_MALE_VOICE: str = os.getenv(
        "HF_TTS_MALE_VOICE",
        "ar-SA-HamedNeural - ar-SA (Male)",
    )
    HF_TTS_FEMALE_VOICE: str = os.getenv(
        "HF_TTS_FEMALE_VOICE",
        "ar-SA-ZariyahNeural - ar-SA (Female)",
    )
    
    # Temp Working Directory
    TEMP_DIR: str = os.getenv("TEMP_DIR", "./temp")

    # Video-generation tuning. Keep all pipeline thresholds in one place.
    MIN_SLIDES: int = int(os.getenv("MIN_SLIDES", "8"))
    TARGET_SLIDES: int = int(os.getenv("TARGET_SLIDES", "10"))
    MAX_SLIDES: int = int(os.getenv("MAX_SLIDES", "16"))
    MIN_SLIDE_DURATION: float = float(os.getenv("MIN_SLIDE_DURATION", "4.0"))
    SLIDE_PADDING: float = float(os.getenv("SLIDE_PADDING", "0.8"))
    GENERATION_RETRY_LIMIT: int = int(os.getenv("GENERATION_RETRY_LIMIT", "1"))
    TTS_RETRY_LIMIT: int = int(os.getenv("TTS_RETRY_LIMIT", "2"))
    VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", "1920"))
    VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", "1080"))
    VIDEO_FPS: int = int(os.getenv("VIDEO_FPS", "25"))
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "48000"))
    MIN_AUDIO_BYTES: int = int(os.getenv("MIN_AUDIO_BYTES", "4096"))
    MIN_VIDEO_BYTES: int = int(os.getenv("MIN_VIDEO_BYTES", "50000"))
    SILENCE_THRESHOLD_DB: float = float(os.getenv("SILENCE_THRESHOLD_DB", "-55"))
    NOTEBOOKLM_FOOTER_HEIGHT_RATIO: float = float(
        os.getenv("NOTEBOOKLM_FOOTER_HEIGHT_RATIO", "0.04")
    )
    NOTEBOOKLM_FOOTER_WIDTH_RATIO: float = float(
        os.getenv("NOTEBOOKLM_FOOTER_WIDTH_RATIO", "0.20")
    )

settings = Settings()
