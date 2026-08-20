import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

import imageio_ffmpeg

from app.core.config import settings


logger = logging.getLogger(__name__)


class MediaValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    path: str
    duration: float
    size_bytes: int
    has_audio: bool
    has_video: bool
    audio_codec: Optional[str] = None
    video_codec: Optional[str] = None
    max_volume_db: Optional[float] = None
    mean_volume_db: Optional[float] = None


def get_ffmpeg_exe() -> str:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not exe or not os.path.exists(exe):
        raise MediaValidationError("FFmpeg binary is unavailable")
    return exe


def _run(command: list[str], label: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="ignore")[-800:]
        raise MediaValidationError(f"{label} failed: {detail}")
    return result


def _parse_duration(stderr: str) -> float:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _inspect_streams(path: str) -> MediaInfo:
    if not path or not os.path.isfile(path):
        raise MediaValidationError("media file does not exist")

    size_bytes = os.path.getsize(path)
    command = [get_ffmpeg_exe(), "-hide_banner", "-i", path, "-f", "null", "-"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = result.stderr.decode("utf-8", errors="ignore")
    if result.returncode != 0:
        raise MediaValidationError(f"media decoding failed: {stderr[-800:]}")

    audio_match = re.search(r"Stream #\S+: Audio:\s*([^,\s]+)", stderr)
    video_match = re.search(r"Stream #\S+: Video:\s*([^,\s]+)", stderr)
    return MediaInfo(
        path=path,
        duration=_parse_duration(stderr),
        size_bytes=size_bytes,
        has_audio=audio_match is not None,
        has_video=video_match is not None,
        audio_codec=audio_match.group(1) if audio_match else None,
        video_codec=video_match.group(1) if video_match else None,
    )


def _measure_volume(path: str) -> tuple[float, float]:
    command = [
        get_ffmpeg_exe(),
        "-hide_banner",
        "-nostats",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = result.stderr.decode("utf-8", errors="ignore")
    if result.returncode != 0:
        raise MediaValidationError(f"audio signal analysis failed: {stderr[-800:]}")

    max_match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", stderr)
    mean_match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", stderr)
    if not max_match or not mean_match:
        raise MediaValidationError("FFmpeg did not report audio signal levels")

    def convert(value: str) -> float:
        return -999.0 if value == "-inf" else float(value)

    return convert(max_match.group(1)), convert(mean_match.group(1))


def validate_audio_file(path: str) -> MediaInfo:
    info = _inspect_streams(path)
    if info.size_bytes < settings.MIN_AUDIO_BYTES:
        raise MediaValidationError(f"audio file is too small ({info.size_bytes} bytes)")
    if not info.has_audio:
        raise MediaValidationError("audio stream is missing")
    if info.duration <= 0:
        raise MediaValidationError("audio duration is zero")

    max_volume, mean_volume = _measure_volume(path)
    if max_volume <= settings.SILENCE_THRESHOLD_DB:
        raise MediaValidationError(
            f"audio is silent (max volume {max_volume:.1f} dB)"
        )
    return MediaInfo(**{**info.__dict__, "max_volume_db": max_volume, "mean_volume_db": mean_volume})


def validate_final_video(
    path: str,
    expected_duration: Optional[float] = None,
) -> MediaInfo:
    info = _inspect_streams(path)
    if info.size_bytes < settings.MIN_VIDEO_BYTES:
        raise MediaValidationError(f"video file is too small ({info.size_bytes} bytes)")
    if not info.has_video:
        raise MediaValidationError("video stream is missing")
    if not info.has_audio:
        raise MediaValidationError("narration audio stream is missing")
    if info.duration <= 0:
        raise MediaValidationError("video duration is zero")
    if expected_duration and abs(info.duration - expected_duration) > max(2.0, expected_duration * 0.03):
        raise MediaValidationError(
            f"video duration {info.duration:.2f}s does not match timeline {expected_duration:.2f}s"
        )

    max_volume, mean_volume = _measure_volume(path)
    if max_volume <= settings.SILENCE_THRESHOLD_DB:
        raise MediaValidationError(
            f"final video audio is silent (max volume {max_volume:.1f} dB)"
        )
    return MediaInfo(**{**info.__dict__, "max_volume_db": max_volume, "mean_volume_db": mean_volume})

