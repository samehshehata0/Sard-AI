import logging
import os
import subprocess
from typing import Tuple

from PIL import Image

from app.core.config import settings
from app.services.media_validation import (
    MediaValidationError,
    get_ffmpeg_exe,
    validate_audio_file,
    validate_final_video,
)
from app.services.video_slide import VideoSlide


logger = logging.getLogger(__name__)


class VideoCompositionError(RuntimeError):
    user_message = "تعذر إنشاء ملف الفيديو النهائي. يرجى إعادة المحاولة."


class VideoComposer:
    def calculate_display_duration(self, audio_duration: float) -> float:
        if audio_duration <= 0:
            raise VideoCompositionError("Narration duration must be positive")
        return max(
            settings.MIN_SLIDE_DURATION,
            audio_duration + settings.SLIDE_PADDING,
        )

    def _run(self, command: list[str], label: str) -> None:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")[-1200:]
            raise VideoCompositionError(f"{label} failed: {stderr}")

    def build_audio_timeline_command(
        self,
        slides: list[VideoSlide],
        output_path: str,
    ) -> list[str]:
        command = [get_ffmpeg_exe(), "-y", "-hide_banner"]
        filters: list[str] = []
        labels: list[str] = []
        for position, slide in enumerate(slides):
            command.extend(["-i", slide.audio_path])
            duration = slide.display_duration
            label = f"a{position}"
            filters.append(
                f"[{position}:a]aresample={settings.AUDIO_SAMPLE_RATE},"
                f"aformat=sample_fmts=fltp:channel_layouts=mono,"
                f"apad=whole_dur={duration:.3f},atrim=0:{duration:.3f}[{label}]"
            )
            labels.append(f"[{label}]")
        filters.append(f"{''.join(labels)}concat=n={len(slides)}:v=0:a=1[aout]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[aout]",
                "-ar",
                str(settings.AUDIO_SAMPLE_RATE),
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                output_path,
            ]
        )
        return command

    def _write_concat_file(self, slides: list[VideoSlide], path: str) -> None:
        with open(path, "w", encoding="utf-8") as concat_file:
            for slide in slides:
                clean_path = os.path.abspath(slide.visual_path).replace("\\", "/").replace("'", "'\\''")
                concat_file.write(f"file '{clean_path}'\n")
                concat_file.write(f"duration {slide.display_duration:.3f}\n")
            final_path = os.path.abspath(slides[-1].visual_path).replace("\\", "/").replace("'", "'\\''")
            concat_file.write(f"file '{final_path}'\n")

    def build_video_command(
        self,
        concat_path: str,
        narration_path: str,
        video_path: str,
        total_duration: float,
    ) -> list[str]:
        scale_filter = (
            f"scale={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={settings.VIDEO_WIDTH}:{settings.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={settings.VIDEO_FPS},format=yuv420p"
        )
        return [
            get_ffmpeg_exe(),
            "-y",
            "-hide_banner",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_path,
            "-i",
            narration_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            str(settings.AUDIO_SAMPLE_RATE),
            "-t",
            f"{total_duration:.3f}",
            "-movflags",
            "+faststart",
            video_path,
        ]

    def _generate_thumbnail(self, slide_path: str, thumbnail_path: str) -> None:
        with Image.open(slide_path) as image:
            image.convert("RGB").save(thumbnail_path, format="JPEG", quality=90)

    async def compose_video(
        self,
        slides: list[VideoSlide],
        output_dir: str,
        narration_output_path: str | None = None,
    ) -> Tuple[str, str, float]:
        if not slides:
            raise VideoCompositionError("No slides were supplied")

        os.makedirs(output_dir, exist_ok=True)
        for slide in slides:
            if not os.path.isfile(slide.visual_path):
                raise VideoCompositionError(f"Missing slide visual: {slide.visual_path}")
            try:
                audio_info = validate_audio_file(slide.audio_path)
            except MediaValidationError as exc:
                raise VideoCompositionError(
                    f"Narration validation failed for slide {slide.index}: {exc}"
                ) from exc
            slide.audio_duration = audio_info.duration
            slide.display_duration = self.calculate_display_duration(audio_info.duration)

        narration_path = narration_output_path or os.path.join(output_dir, "narration.mp3")
        video_path = os.path.join(output_dir, "final_story.mp4")
        thumbnail_path = os.path.join(output_dir, "thumbnail.jpg")
        concat_path = os.path.join(output_dir, "slides.concat.txt")
        total_duration = sum(slide.display_duration for slide in slides)

        logger.info("[Sard] Total narration timeline duration: %.2fs", total_duration)
        self._run(
            self.build_audio_timeline_command(slides, narration_path),
            "audio timeline composition",
        )
        combined_audio = validate_audio_file(narration_path)
        logger.info(
            "[Sard] Combined narration validation: OK duration=%.2fs max_volume=%.1fdB",
            combined_audio.duration,
            combined_audio.max_volume_db,
        )

        self._write_concat_file(slides, concat_path)
        logger.info("[Sard] Rendering final video")
        self._run(
            self.build_video_command(concat_path, narration_path, video_path, total_duration),
            "final MP4 encoding",
        )
        final_info = validate_final_video(video_path, expected_duration=total_duration)
        self._generate_thumbnail(slides[0].visual_path, thumbnail_path)
        logger.info(
            "[Sard] Video validation: OK duration=%.2fs audio_max=%.1fdB",
            final_info.duration,
            final_info.max_volume_db,
        )
        return video_path, thumbnail_path, final_info.duration
