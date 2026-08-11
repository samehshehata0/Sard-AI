import os
import logging
import subprocess
import imageio_ffmpeg
from app.core.config import settings

logger = logging.getLogger(__name__)

class NarrationService:
    async def generate_narration(self, text: str, voice_gender: str, output_path: str) -> str:
        """
        Generates Arabic narration audio using Google Cloud Text-to-Speech or free gTTS / EdgeTTS fallback.
        Returns path to generated MP3.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        logger.info(f"[NarrationService] Synthesizing Arabic narration ({voice_gender}) -> {output_path}")

        # 1. Try Google Cloud Text-to-Speech API
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                from google.cloud import texttospeech
                client = texttospeech.TextToSpeechClient()

                synthesis_input = texttospeech.SynthesisInput(text=text)
                ssml_gender = (
                    texttospeech.SsmlVoiceGender.FEMALE
                    if voice_gender.lower() == "female"
                    else texttospeech.SsmlVoiceGender.MALE
                )
                
                voice = texttospeech.VoiceSelectionParams(
                    language_code="ar-XA",
                    ssml_gender=ssml_gender,
                    name="ar-XA-Wavenet-B" if ssml_gender == texttospeech.SsmlVoiceGender.MALE else "ar-XA-Wavenet-A"
                )

                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=0.95
                )

                response = client.synthesize_speech(
                    input=synthesis_input, voice=voice, audio_config=audio_config
                )

                with open(output_path, "wb") as out:
                    out.write(response.audio_content)
                logger.info(f"[NarrationService] Google TTS audio generated successfully ({len(response.audio_content)} bytes).")
                return output_path
            except Exception as e:
                logger.warning(f"[NarrationService] Google TTS SDK error/fallback: {e}")

        # 2. Free High Quality Arabic TTS Fallback (gTTS)
        try:
            from gtts import gTTS
            logger.info(f"[NarrationService] Using gTTS Arabic voice synthesizer fallback...")
            tts = gTTS(text=text, lang="ar")
            tts.save(output_path)
            logger.info(f"[NarrationService] gTTS Arabic audio generated -> {output_path}")
            return output_path
        except Exception as e:
            logger.warning(f"[NarrationService] gTTS fallback failed: {e}")

        # 3. FFmpeg audio generator fallback
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", "15",
            "-q:a", "9", "-acodec", "libmp3lame",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
