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
                private_key=settings.IMAGEKIT_PRIVATE_KEY,
            )
        else:
            self.imagekit = None

    def _to_http_url(self, local_path: str) -> str:
        rel = os.path.relpath(local_path, settings.TEMP_DIR).replace("\\", "/")
        return f"http://127.0.0.1:8000/temp/{rel}"

    async def upload_assets(
        self,
        presentation_path: str,
        story_id: str,
        video_path: str = "",
        thumbnail_path: str = "",
        narration_path: str = "",
    ) -> Dict[str, str]:
        """
        Uploads presentation, and any of video/thumbnail/narration that were
        actually produced, to ImageKit or serves them via HTTP static server.
        video_path/thumbnail_path/narration_path may be empty when a lighter
        output mode (text-only, or text+audio) skipped that stage — in that
        case the corresponding *_url key is simply omitted from the result
        instead of pointing at a file that was never created.
        Returns dict containing presentation_url and whichever of
        video_url/thumbnail_url/narration_audio_url apply.
        """
        logger.info(f"[ImageKitUploader] Uploading assets for story_id: {story_id}")

        if not self.imagekit:
            logger.warning("[ImageKitUploader] ImageKit credentials not configured. Serving assets via HTTP static server.")
            urls = {"presentation_url": self._to_http_url(presentation_path)}
            if video_path:
                urls["video_url"] = self._to_http_url(video_path)
            if thumbnail_path:
                urls["thumbnail_url"] = self._to_http_url(thumbnail_path)
            if narration_path:
                urls["narration_audio_url"] = self._to_http_url(narration_path)
            return urls

        urls = {}
        assets = [("presentation", presentation_path, f"presentation_{story_id}.pdf")]
        if video_path:
            assets.append(("video", video_path, f"video_{story_id}.mp4"))
        if thumbnail_path:
            assets.append(("thumbnail", thumbnail_path, f"thumbnail_{story_id}.jpg"))
        if narration_path:
            assets.append(("narration_audio", narration_path, f"narration_{story_id}.mp3"))

        for asset_key, local_file, remote_name in assets:
            if os.path.exists(local_file):
                try:
                    with open(local_file, "rb") as file_data:
                        res = self.imagekit.files.upload(
                            file=file_data.read(),
                            file_name=remote_name,
                            folder="/sard_ai_stories/",
                            public_key=settings.IMAGEKIT_PUBLIC_KEY,
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
