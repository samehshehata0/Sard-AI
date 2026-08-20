import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.api import endpoints
from app.core.config import settings
from app.schemas.story import StoryGenerationRequest
from app.services.media_validation import (
    MediaValidationError,
    get_ffmpeg_exe,
    validate_audio_file,
    validate_final_video,
)
from app.services.narration_builder import NarrationBuilder
from app.services.narration_service import NarrationGenerationError, NarrationService
from app.services.notebooklm_service import NotebookLMGenerationError, NotebookLMService
from app.services.prompt_builder import PromptBuilder
from app.services.slide_extractor import SlideExtractor
from app.services.video_composer import VideoComposer
from app.services.video_slide import VideoSlide


def request_fixture(story_id: str = "water-story") -> StoryGenerationRequest:
    return StoryGenerationRequest(
        story_id=story_id,
        story_title="رحلة قطرة ماء",
        story_idea="أهمية الحفاظ على الماء وترشيد استهلاكه في البيت والمدرسة",
        education_level="المرحلة الابتدائية",
        story_duration="تلقائي حسب المحتوى",
        learning_objectives=["أن يشرح المتعلم أهمية ترشيد استهلاك الماء."],
        student_age="9–11 سنوات",
        student_level="مبتدئ",
        learning_needs="أمثلة بصرية واضحة",
        story_style="حواري",
        voice_tone="مشجعة",
        narrator_gender="female",
        output_type="نص + صوت + فيديو",
    )


def make_tone(path: Path, duration: float = 0.55) -> None:
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=700:sample_rate=48000",
        "-t",
        str(duration),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_silence(path: Path) -> None:
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=mono",
        "-t",
        "1",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_slide(path: Path, number: int, size: tuple[int, int] = (640, 360)) -> None:
    image = Image.new("RGB", size, (245, 248, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle((30 + number * 4, 30, 250 + number * 8, 180), fill=(20 * number, 90, 180))
    draw.line((0, number * 20 % size[1], size[0], (number * 47) % size[1]), fill=(220, 90, 20), width=8)
    draw.text((300, 150), str(number), fill=(0, 0, 0))
    image.save(path)


def test_narration_text_is_meaningful_and_has_no_production_metadata(tmp_path):
    paths = []
    for index in range(8):
        path = tmp_path / f"scene_{index + 1:02d}.png"
        make_slide(path, index + 1)
        paths.append(str(path))
    slides = NarrationBuilder().build(
        request_fixture(),
        paths,
        ["Slide 1\nNotebookLM Presentation\nالحفاظ على الماء"] * 8,
    )
    assert len(slides) == 8
    assert all(len(slide.narration_text.split()) >= 20 for slide in slides)
    assert all("Slide" not in slide.narration_text for slide in slides)
    assert all("NotebookLM" not in slide.narration_text for slide in slides)


def test_empty_narration_is_rejected(tmp_path):
    with pytest.raises(NarrationGenerationError):
        asyncio.run(NarrationService().generate_narration("   ", "female", str(tmp_path / "empty.mp3")))


def test_silent_audio_is_rejected(tmp_path):
    path = tmp_path / "silent.mp3"
    make_silence(path)
    with pytest.raises(MediaValidationError, match="silent"):
        validate_audio_file(str(path))


def test_valid_audio_is_detected(tmp_path):
    path = tmp_path / "tone.mp3"
    make_tone(path)
    info = validate_audio_file(str(path))
    assert info.duration > 0
    assert info.max_volume_db > settings.SILENCE_THRESHOLD_DB


def test_slide_target_and_expansion_prompt():
    builder = PromptBuilder()
    req = request_fixture()
    assert settings.MIN_SLIDES <= builder.estimate_target_slide_count(req) <= settings.MAX_SLIDES
    prompt = builder.build_notebooklm_prompt(req, expansion_retry=True)
    assert "Do not compress" in prompt
    assert "distinct visual sections" in prompt
    assert str(settings.MIN_SLIDES) in prompt


def test_notebooklm_pending_job_can_be_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_RESUME_MAX_AGE_SECONDS", 1800)
    service = NotebookLMService()
    notebook_url = "https://notebooklm.google.com/notebook/example-job"

    service._save_job_state(str(tmp_path), notebook_url)

    assert service._resumable_notebook_url(str(tmp_path)) == notebook_url


def test_notebooklm_stale_job_is_not_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NOTEBOOKLM_RESUME_MAX_AGE_SECONDS", 60)
    state_path = tmp_path / "notebooklm_job.json"
    state_path.write_text(
        json.dumps(
            {
                "notebook_url": "https://notebooklm.google.com/notebook/stale-job",
                "created_at_epoch": time.time() - 61,
            }
        ),
        encoding="utf-8",
    )

    assert NotebookLMService()._resumable_notebook_url(str(tmp_path)) is None


def test_slide_ordering_is_preserved(tmp_path):
    paths = [str(tmp_path / f"scene_{index:02d}.png") for index in range(1, 9)]
    slides = NarrationBuilder().build(request_fixture(), paths)
    assert [slide.index for slide in slides] == list(range(1, 9))
    assert [slide.visual_path for slide in slides] == paths


def test_dynamic_duration_calculation(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SLIDE_DURATION", 4.0)
    monkeypatch.setattr(settings, "SLIDE_PADDING", 0.8)
    composer = VideoComposer()
    assert composer.calculate_display_duration(2.0) == 4.0
    assert composer.calculate_display_duration(8.0) == pytest.approx(8.8)


def test_duplicate_slide_filter_keeps_order(tmp_path):
    first = tmp_path / "scene_01.png"
    duplicate = tmp_path / "scene_02.png"
    third = tmp_path / "scene_03.png"
    make_slide(first, 1)
    duplicate.write_bytes(first.read_bytes())
    make_slide(third, 7)
    unique = SlideExtractor().remove_duplicate_slides([str(first), str(duplicate), str(third)])
    assert unique == [str(first), str(third)]


def test_ffmpeg_commands_map_video_and_audio(tmp_path):
    composer = VideoComposer()
    slides = [
        VideoSlide(1, "أ", "one.png", "نص", "one.mp3", 1.0, 1.5),
        VideoSlide(2, "ب", "two.png", "نص", "two.mp3", 2.0, 2.5),
    ]
    audio_command = composer.build_audio_timeline_command(slides, str(tmp_path / "narration.mp3"))
    assert "concat=n=2:v=0:a=1" in audio_command[audio_command.index("-filter_complex") + 1]
    assert audio_command.index("one.mp3") < audio_command.index("two.mp3")

    video_command = composer.build_video_command("slides.txt", "narration.mp3", "final.mp4", 4.0)
    mappings = [video_command[index + 1] for index, value in enumerate(video_command) if value == "-map"]
    assert mappings == ["0:v:0", "1:a:0"]
    assert "libx264" in video_command
    assert "aac" in video_command
    assert "yuv420p" in video_command


def test_multi_slide_composition_and_final_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_WIDTH", 320)
    monkeypatch.setattr(settings, "VIDEO_HEIGHT", 180)
    monkeypatch.setattr(settings, "VIDEO_FPS", 10)
    monkeypatch.setattr(settings, "MIN_SLIDE_DURATION", 0.7)
    monkeypatch.setattr(settings, "SLIDE_PADDING", 0.1)
    monkeypatch.setattr(settings, "MIN_VIDEO_BYTES", 1000)
    slides = []
    for index in range(2):
        image_path = tmp_path / f"scene_{index + 1:02d}.png"
        audio_path = tmp_path / f"scene_{index + 1:02d}.mp3"
        make_slide(image_path, index + 1, (320, 180))
        make_tone(audio_path)
        slides.append(VideoSlide(index + 1, "عنوان", str(image_path), "شرح", str(audio_path)))

    video_path, _, duration = asyncio.run(
        VideoComposer().compose_video(slides, str(tmp_path / "video"), str(tmp_path / "narration.mp3"))
    )
    info = validate_final_video(video_path, duration)
    assert info.has_video and info.has_audio
    assert info.max_volume_db > settings.SILENCE_THRESHOLD_DB
    assert slides[0].display_duration > slides[0].audio_duration


def test_generation_failure_never_returns_completed(monkeypatch, tmp_path):
    async def fail_notebook(self, file_path, prompt, target_dir):
        raise NotebookLMGenerationError("automation unavailable")

    monkeypatch.setattr(settings, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(NotebookLMService, "run_pipeline", fail_notebook)
    with pytest.raises(Exception) as raised:
        asyncio.run(endpoints.generate_story(request_fixture("failure-story")))
    assert getattr(raised.value, "detail", "") == NotebookLMGenerationError.user_message
    assert endpoints.story_repository.get_story_record("failure-story")["status"] == "failed"


def test_insufficient_slide_count_retries_once_then_fails(monkeypatch, tmp_path):
    artifact = tmp_path / "short.pdf"
    artifact.write_bytes(b"%PDF" + b"x" * 12_000)
    attempts = 0

    async def fake_notebook(self, file_path, prompt, target_dir):
        nonlocal attempts
        attempts += 1
        return str(artifact)

    async def four_slides(presentation_path, output_dir):
        return [str(tmp_path / f"scene_{index:02d}.png") for index in range(1, 5)]

    monkeypatch.setattr(settings, "TEMP_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(settings, "MIN_SLIDES", 8)
    monkeypatch.setattr(settings, "GENERATION_RETRY_LIMIT", 1)
    monkeypatch.setattr(NotebookLMService, "run_pipeline", fake_notebook)
    monkeypatch.setattr(endpoints.slide_extractor, "extract_slides", four_slides)
    monkeypatch.setattr(endpoints.slide_extractor, "extract_slide_texts", lambda path: [""] * 4)

    with pytest.raises(Exception) as raised:
        asyncio.run(endpoints.generate_story(request_fixture("short-story")))
    assert attempts == 2
    assert getattr(raised.value, "detail", "") == NotebookLMGenerationError.user_message


def test_successful_eight_slide_generation(monkeypatch, tmp_path):
    visuals = []
    for index in range(8):
        path = tmp_path / f"source_scene_{index + 1:02d}.png"
        make_slide(path, index + 1, (320, 180))
        visuals.append(str(path))
    artifact = tmp_path / "notebooklm_presentation.pdf"
    artifact.write_bytes(b"%PDF synthetic NotebookLM artifact" + b"x" * 12_000)

    async def fake_notebook(self, file_path, prompt, target_dir):
        return str(artifact)

    async def fake_extract(presentation_path, output_dir):
        return visuals

    async def fake_narration(text, voice_gender, output_path, voice_tone=""):
        make_tone(Path(output_path), 0.45)
        return output_path

    async def fake_upload(**kwargs):
        return {
            "presentation_url": "http://local/presentation.pdf",
            "video_url": "http://local/final_story.mp4",
            "thumbnail_url": "http://local/thumbnail.jpg",
        }

    monkeypatch.setattr(settings, "TEMP_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(settings, "MIN_SLIDES", 8)
    monkeypatch.setattr(settings, "VIDEO_WIDTH", 320)
    monkeypatch.setattr(settings, "VIDEO_HEIGHT", 180)
    monkeypatch.setattr(settings, "VIDEO_FPS", 10)
    monkeypatch.setattr(settings, "MIN_SLIDE_DURATION", 0.55)
    monkeypatch.setattr(settings, "SLIDE_PADDING", 0.05)
    monkeypatch.setattr(settings, "MIN_VIDEO_BYTES", 1000)
    monkeypatch.setattr(NotebookLMService, "run_pipeline", fake_notebook)
    monkeypatch.setattr(endpoints.slide_extractor, "extract_slides", fake_extract)
    monkeypatch.setattr(endpoints.slide_extractor, "extract_slide_texts", lambda path: ["فكرة تعليمية"] * 8)
    monkeypatch.setattr(endpoints.narration_service, "generate_narration", fake_narration)
    monkeypatch.setattr(endpoints.imagekit_uploader, "upload_assets", fake_upload)
    monkeypatch.setattr(endpoints.story_repository, "save_story_record", lambda record: True)

    result = asyncio.run(endpoints.generate_story(request_fixture("success-story")))
    assert result.status == "completed"
    assert len(result.scenes) == 8
    assert result.duration_seconds > 0
    assert result.narration_audio_url.endswith("narration.mp3")
    assert all(scene.duration_seconds > 0 for scene in result.scenes)
