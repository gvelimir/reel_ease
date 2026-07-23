"""Configuration for a single reel build."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def resolve_caption_font(explicit_path: str | None) -> str:
    """Return a usable .ttf path for caption rendering, or raise if none found.

    moviepy 2.x requires an explicit font file for TextClip, so we fail loudly
    rather than let it fall back to an unpredictable default.
    """
    if explicit_path:
        if not Path(explicit_path).is_file():
            raise FileNotFoundError(f"Caption font not found: {explicit_path}")
        return explicit_path
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    discovered = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    if discovered:
        return discovered[0]
    raise FileNotFoundError(
        "No .ttf font found for captions. Install one (e.g. fonts-dejavu-core) "
        "or pass --font /path/to/font.ttf"
    )


@dataclass
class ReelConfig:
    """Everything one reel build needs. Paths are validated on load()."""

    video_paths: list[Path]
    output_path: Path

    caption_file: Path | None = None
    youtube_url: str | None = None

    target_duration: float = 30.0
    max_clip_seconds: float = 4.0
    min_scene_seconds: float = 1.0
    scene_threshold: float = 27.0
    scene_frame_skip: int = 2  # sample every (skip+1)th frame during detection
    scene_downscale: int | None = None  # None -> PySceneDetect auto-downscale
    scene_workers: int | None = None  # None -> one process per video (cpu-capped)

    width: int = 1080
    height: int = 1920
    fps: int = 30
    x264_preset: str = "veryfast"  # encode speed/size tradeoff for the ffmpeg passes

    use_ai: bool = True
    openai_model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
    )
    font_path: str | None = None
    caption_backend: str = "ffmpeg"  # "ffmpeg" (fast drawtext) or "moviepy"

    keep_original_audio: bool = False
    music_volume: float = 1.0
    original_audio_volume: float = 0.25
    music_start: float | None = None  # None -> derive from the URL's t= param
    music_file: Path | None = None  # local audio; skips the YouTube download
    cookies_file: Path | None = None
    cookies_from_browser: str | None = None

    def has_music(self) -> bool:
        return bool(self.youtube_url or self.music_file)

    def caption_lines(self) -> list[str]:
        """Non-empty caption lines from the caption file, in order."""
        if not self.caption_file:
            return []
        raw = self.caption_file.read_text(encoding="utf-8")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def validate(self) -> None:
        missing = [str(path) for path in self.video_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Video(s) not found: {', '.join(missing)}")
        if not self.video_paths:
            raise ValueError("At least one input video is required.")
        if self.caption_file and not self.caption_file.is_file():
            raise FileNotFoundError(f"Caption file not found: {self.caption_file}")
        if self.music_file and not self.music_file.is_file():
            raise FileNotFoundError(f"Music file not found: {self.music_file}")
        if self.target_duration <= 0:
            raise ValueError("target_duration must be positive.")
        if self.caption_backend not in ("ffmpeg", "moviepy"):
            raise ValueError("caption_backend must be 'ffmpeg' or 'moviepy'.")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
