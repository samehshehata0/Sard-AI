from dataclasses import dataclass


@dataclass
class VideoSlide:
    index: int
    title: str
    visual_path: str
    narration_text: str
    audio_path: str = ""
    audio_duration: float = 0.0
    display_duration: float = 0.0

