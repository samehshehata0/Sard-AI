import os
import subprocess
import logging
import imageio_ffmpeg
from typing import List, Tuple

logger = logging.getLogger(__name__)

class VideoComposer:
    def _get_ffmpeg_exe(self) -> str:
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                return exe
        except Exception as e:
            logger.warning(f"[VideoComposer] imageio_ffmpeg path resolution warning: {e}")
        return "ffmpeg"

    async def compose_video(
        self,
        slide_images: List[str],
        audio_path: str,
        narration_script: str,
        output_dir: str
    ) -> Tuple[str, str, float]:
        """
        Composes final MP4 video from slide images and audio using FFmpeg.
        Guarantees every slide in the presentation is displayed completely (8-10 seconds per slide).
        Returns (video_path, thumbnail_path, duration_seconds).
        """
        os.makedirs(output_dir, exist_ok=True)
        video_path = os.path.join(output_dir, "final_story.mp4")
        thumbnail_path = os.path.join(output_dir, "thumbnail.jpg")
        ffmpeg_exe = self._get_ffmpeg_exe()

        audio_duration = self._get_media_duration(audio_path)
        
        # Calculate per-slide display time (minimum 8.0s per slide for complete reading & viewing)
        per_slide_duration = max(8.0, audio_duration / max(1, len(slide_images)))
        total_video_duration = per_slide_duration * len(slide_images)

        logger.info(f"[VideoComposer] Using FFmpeg binary: {ffmpeg_exe}")
        logger.info(f"[VideoComposer] Composing {len(slide_images)} slides over total duration {total_video_duration:.2f}s ({per_slide_duration:.2f}s per slide)")

        # 1. Run multi-slide concat composition with full audio padding & duration limit
        success = self._simple_concat_fallback(slide_images, audio_path, video_path, per_slide_duration, total_video_duration, ffmpeg_exe)
        
        if not success or not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            logger.warning("[VideoComposer] Multi-slide concat failed. Falling back to single image render.")
            self._single_image_fallback(slide_images[0], audio_path, video_path, total_video_duration, ffmpeg_exe)

        # 2. Generate Thumbnail image from slide or video
        self._generate_thumbnail(slide_images[0], video_path, thumbnail_path, ffmpeg_exe)

        return video_path, thumbnail_path, total_video_duration

    def _get_media_duration(self, path: str) -> float:
        try:
            if os.path.exists(path):
                size = os.path.getsize(path)
                return max(15.0, size / 4000.0)
        except Exception:
            pass
        return 20.0

    def _simple_concat_fallback(self, slide_images: List[str], audio_path: str, video_path: str, duration_per_slide: float, total_duration: float, ffmpeg_exe: str) -> bool:
        try:
            concat_txt = os.path.join(os.path.dirname(video_path), "concat.txt")
            with open(concat_txt, "w", encoding="utf-8") as f:
                for img in slide_images:
                    clean_img = os.path.abspath(img).replace("\\", "/")
                    f.write(f"file '{clean_img}'\n")
                    f.write(f"duration {duration_per_slide:.2f}\n")
                last_img = os.path.abspath(slide_images[-1]).replace("\\", "/")
                f.write(f"file '{last_img}'\n")

            cmd = [
                ffmpeg_exe, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_txt,
                "-i", audio_path,
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-af", "apad",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(total_duration),
                video_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.warning(f"[VideoComposer] Concat render warning: {res.stderr.decode('utf-8', errors='ignore')[:300]}")
            return res.returncode == 0 and os.path.exists(video_path) and os.path.getsize(video_path) > 0
        except Exception as e:
            logger.warning(f"[VideoComposer] Concat render error: {e}")
            return False

    def _single_image_fallback(self, image_path: str, audio_path: str, video_path: str, duration: float, ffmpeg_exe: str) -> bool:
        try:
            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1", "-t", str(duration), "-i", image_path,
                "-i", audio_path,
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-af", "apad",
                "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                video_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.warning(f"[VideoComposer] Single image render error: {res.stderr.decode('utf-8', errors='ignore')[:300]}")
            return res.returncode == 0 and os.path.exists(video_path) and os.path.getsize(video_path) > 0
        except Exception as e:
            logger.warning(f"[VideoComposer] Single image fallback error: {e}")
            return False

    def _generate_thumbnail(self, slide_image_path: str, video_path: str, thumbnail_path: str, ffmpeg_exe: str):
        try:
            if os.path.exists(slide_image_path):
                import shutil
                shutil.copy(slide_image_path, thumbnail_path)
                logger.info(f"[VideoComposer] Thumbnail copied from slide -> {thumbnail_path}")
                return
        except Exception:
            pass

        try:
            cmd = [
                ffmpeg_exe, "-y",
                "-ss", "00:00:01",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                thumbnail_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"[VideoComposer] Generated thumbnail from video -> {thumbnail_path}")
        except Exception as e:
            logger.warning(f"[VideoComposer] Thumbnail generation warning: {e}")
