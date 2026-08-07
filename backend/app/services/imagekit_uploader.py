import os
import logging
from typing import Dict
from imagekitio import ImageKit
from app.core.config import settings

logger = logging.getLogger(__name__)

class ImageKitUploader:
    def __init__(self):
        if settings.IMAGEKIT_PUBLIC_KEY and settings.IMAGEKIT_PRIVATE_KEY and settings.IMAGEKIT_URL_ENDPOINT:
            self.imagekit = ImageKit(
                public_key=settings.IMAGEKIT_PUBLIC_KEY,
                private_key=settings.IMAGEKIT_PRIVATE_KEY,
                url_endpoint=settings.IMAGEKIT_URL_ENDPOINT
            )
        else:
            self.imagekit = None

    def _to_http_url(self, local_path: str) -> str:
        rel = os.path.relpath(local_path, settings.TEMP_DIR).replace("\\", "/")
        return f"http://127.0.0.1:8000/temp/{rel}"

    async def upload_assets(
        self,
        presentation_path: str,
        video_path: str,
        thumbnail_path: str,
        story_id: str
    ) -> Dict[str, str]:
        """
        Uploads presentation, video, and thumbnail to ImageKit or serves via HTTP static server.
        Returns dict containing presentation_url, video_url, thumbnail_url.
        """
        logger.info(f"[ImageKitUploader] Uploading assets for story_id: {story_id}")

        if not self.imagekit:
            logger.warning("[ImageKitUploader] ImageKit credentials not configured. Serving assets via HTTP static server.")
            return {
                "presentation_url": self._to_http_url(presentation_path),
                "video_url": self._to_http_url(video_path),
                "thumbnail_url": self._to_http_url(thumbnail_path)
            }

        urls = {}
        assets = [
            ("presentation", presentation_path, f"presentation_{story_id}.pdf"),
            ("video", video_path, f"video_{story_id}.mp4"),
            ("thumbnail", thumbnail_path, f"thumbnail_{story_id}.jpg")
        ]

        for asset_key, local_file, remote_name in assets:
            if os.path.exists(local_file):
                try:
                    with open(local_file, "rb") as file_data:
                        res = self.imagekit.upload_file(
                            file=file_data,
                            file_name=remote_name,
                            options={"folder": "/sard_ai_stories/"}
                        )
                        url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else "")
                        urls[f"{asset_key}_url"] = url
                        logger.info(f"[ImageKitUploader] Uploaded {asset_key} -> {url}")
                except Exception as e:
                    logger.warning(f"[ImageKitUploader] Upload error for {asset_key}: {e}. Fallback to HTTP URL.")
                    urls[f"{asset_key}_url"] = self._to_http_url(local_file)
            else:
                urls[f"{asset_key}_url"] = ""

        return urls
