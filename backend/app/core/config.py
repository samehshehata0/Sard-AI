import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
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
    NOTEBOOKLM_STORAGE_STATE_PATH: str = os.getenv(
        "NOTEBOOKLM_STORAGE_STATE_PATH",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage_state.json"))
    )
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
    
    # Temp Working Directory
    TEMP_DIR: str = os.getenv("TEMP_DIR", "./temp")

    class Config:
        case_sensitive = True

settings = Settings()
