import json
import logging
import os
import shutil
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.media_validation import MediaInfo, MediaValidationError, validate_audio_file


logger = logging.getLogger(__name__)


class NarrationGenerationError(RuntimeError):
    user_message = "تعذر إنشاء التعليق الصوتي للقصة. يرجى إعادة المحاولة."


class NarrationService:
    def _is_female(self, voice_gender: str) -> bool:
        value = (voice_gender or "").strip().lower()
        return value in {"female", "f", "أنثى", "انثى", "نسائي", "امرأة"}

    def _speech_rate(self, voice_tone: str) -> int:
        tone = (voice_tone or "").lower()
        if any(word in tone for word in ("هادئ", "بطيء", "متأن")):
            return -8
        if any(word in tone for word in ("سريع", "حيوي", "نشيط")):
            return 5
        return -3

    def _google_tts(self, text: str, voice_gender: str, voice_tone: str, output_path: str) -> None:
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()
        female = self._is_female(voice_gender)
        gender = (
            texttospeech.SsmlVoiceGender.FEMALE
            if female
            else texttospeech.SsmlVoiceGender.MALE
        )
        voice = texttospeech.VoiceSelectionParams(
            language_code="ar-XA",
            ssml_gender=gender,
            name="ar-XA-Wavenet-A" if female else "ar-XA-Wavenet-B",
        )
        rate = 1.0 + (self._speech_rate(voice_tone) / 100.0)
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=voice,
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=rate,
            ),
        )
        if not response.audio_content:
            raise NarrationGenerationError("Google TTS returned no audio bytes")
        Path(output_path).write_bytes(response.audio_content)

    def _parse_gradio_result(self, body: str) -> str:
        for line in body.splitlines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if not data or not isinstance(data[0], dict):
                continue
            url = data[0].get("url")
            if url:
                return str(url)
        raise NarrationGenerationError("Hugging Face TTS returned no audio URL")

    def _huggingface_tts(
        self,
        text: str,
        voice_gender: str,
        voice_tone: str,
        output_path: str,
    ) -> None:
        endpoint = settings.HF_TTS_ENDPOINT.rstrip("/")
        voice = (
            settings.HF_TTS_FEMALE_VOICE
            if self._is_female(voice_gender)
            else settings.HF_TTS_MALE_VOICE
        )
        headers = {}
        if settings.HF_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.HF_API_TOKEN}"

        payload = {"data": [text, voice, self._speech_rate(voice_tone), 0]}
        timeout = httpx.Timeout(120.0, connect=30.0)
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            event_id = response.json().get("event_id")
            if not event_id:
                raise NarrationGenerationError("Hugging Face TTS returned no event id")

            result = client.get(f"{endpoint}/{event_id}")
            result.raise_for_status()
            audio_url = self._parse_gradio_result(result.text)
            audio_response = client.get(audio_url)
            audio_response.raise_for_status()
            if not audio_response.content:
                raise NarrationGenerationError("Hugging Face TTS returned empty audio")
            Path(output_path).write_bytes(audio_response.content)

    def _gtts(self, text: str, output_path: str) -> None:
        from gtts import gTTS

        gTTS(text=text, lang="ar").save(output_path)

    async def generate_narration(
        self,
        text: str,
        voice_gender: str,
        output_path: str,
        voice_tone: str = "",
    ) -> str:
        clean_text = (text or "").strip()
        if not clean_text:
            raise NarrationGenerationError("Narration text is empty")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        logger.info(
            "[Sard] Narration synthesis started: characters=%s gender=%s",
            len(clean_text),
            voice_gender,
        )

        providers = []
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            providers.append(("google-cloud-tts", self._google_tts))
        providers.extend(
            [
                ("huggingface-edge-tts", self._huggingface_tts),
                ("gtts", lambda text, gender, tone, path: self._gtts(text, path)),
            ]
        )

        failures: list[str] = []
        attempts_per_provider = max(1, settings.TTS_RETRY_LIMIT)
        for provider_name, provider in providers:
            for attempt in range(1, attempts_per_provider + 1):
                attempt_path = f"{output_path}.{provider_name}.{attempt}.tmp.mp3"
                try:
                    provider(clean_text, voice_gender, voice_tone, attempt_path)
                    info = validate_audio_file(attempt_path)
                    shutil.move(attempt_path, output_path)
                    logger.info(
                        "[Sard] Narration audio validated: provider=%s duration=%.2fs max_volume=%.1fdB bytes=%s",
                        provider_name,
                        info.duration,
                        info.max_volume_db,
                        info.size_bytes,
                    )
                    return output_path
                except Exception as exc:
                    failures.append(f"{provider_name} attempt {attempt}: {exc}")
                    logger.warning(
                        "[Sard] Narration provider failed: provider=%s attempt=%s error=%s",
                        provider_name,
                        attempt,
                        exc,
                    )
                    try:
                        os.remove(attempt_path)
                    except FileNotFoundError:
                        pass

        logger.error("[Sard] All narration providers failed: %s", " | ".join(failures))
        raise NarrationGenerationError("All narration providers failed validation")

    def validate(self, path: str) -> MediaInfo:
        try:
            return validate_audio_file(path)
        except MediaValidationError as exc:
            raise NarrationGenerationError(str(exc)) from exc
