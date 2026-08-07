import os
import logging

logger = logging.getLogger(__name__)

class PresentationDownloader:
    async def verify_and_locate(self, download_path: str) -> str:
        """
        Verifies that the presentation file exists and returns absolute path.
        """
        if not os.path.exists(download_path):
            raise FileNotFoundError(f"Presentation file not found at: {download_path}")
        logger.info(f"[PresentationDownloader] File located: {download_path} ({os.path.getsize(download_path)} bytes)")
        return os.path.abspath(download_path)
