"""Orchestrate the reel pipeline: assemble -> music -> captions -> output.

Assembly and music muxing run in ffmpeg (see video_assembly / music). Captions
use the fast ffmpeg backend by default; the moviepy backend is kept as an
opt-in that re-reads the rendered base and composites TextClips.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from reel_ease.caption_ffmpeg import burn_captions
from reel_ease.caption_overlay import build_caption_clips
from reel_ease.config import ReelConfig, resolve_caption_font
from reel_ease.highlight_selector import HighlightSelection, select_highlights
from reel_ease.music import add_music
from reel_ease.scene_detection import detect_all_segments
from reel_ease.video_assembly import assemble_base_video


def build_reel(config: ReelConfig) -> HighlightSelection:
    """Run the full pipeline and write config.output_path. Returns the selection."""
    config.validate()
    font_path = resolve_caption_font(config.font_path)

    segments = detect_all_segments(
        config.video_paths,
        config.scene_threshold,
        config.min_scene_seconds,
        config.max_clip_seconds,
        frame_skip=config.scene_frame_skip,
        downscale=config.scene_downscale,
        workers=config.scene_workers,
    )
    if not segments:
        raise RuntimeError("No usable scenes were found in the input videos.")

    selection = select_highlights(
        segments,
        config.target_duration,
        config.max_clip_seconds,
        config.use_ai,
        config.openai_model,
    )
    total_duration = sum(segment.duration for segment in selection.segments)

    work_dir = Path(tempfile.mkdtemp(prefix="reel_ease_"))
    video_stage = _render_video_stage(selection, config, work_dir, total_duration)
    _render_captions(video_stage, config, font_path, total_duration)
    return selection


def _render_video_stage(
    selection: HighlightSelection,
    config: ReelConfig,
    work_dir: Path,
    total_duration: float,
) -> Path:
    """Assemble the base video and mux music, returning the file to caption."""
    keep_source_audio = config.keep_original_audio or not config.has_music()
    base_path = work_dir / "base.mp4"
    base_has_audio = assemble_base_video(
        selection.segments, config, base_path, keep_source_audio
    )

    if not config.has_music():
        return base_path

    mixed_path = work_dir / "mixed.mp4"
    try:
        add_music(base_path, mixed_path, config, total_duration, base_has_audio)
    except Exception as error:  # noqa: BLE001 - still deliver a reel without music
        print(f"warning: music step failed, writing reel without it: {error}")
        return base_path
    return mixed_path


def _render_captions(
    video_stage: Path, config: ReelConfig, font_path: str, total_duration: float
) -> None:
    """Write the final output, applying captions via the configured backend."""
    caption_lines = config.caption_lines()

    if not caption_lines:
        shutil.copyfile(video_stage, config.output_path)
        return

    if config.caption_backend == "moviepy":
        _captions_moviepy(video_stage, config, font_path)
        return

    burn_captions(
        video_stage,
        config.output_path,
        caption_lines,
        total_duration,
        config.width,
        config.height,
        font_path,
        preset=config.x264_preset,
    )


def _captions_moviepy(video_stage: Path, config: ReelConfig, font_path: str) -> None:
    """Slower pure-moviepy overlay: re-read the base and composite TextClips."""
    from moviepy import CompositeVideoClip, VideoFileClip

    clip = VideoFileClip(str(video_stage))
    try:
        caption_clips = build_caption_clips(
            config.caption_lines(), clip.duration, config.width, config.height, font_path
        )
        composed = CompositeVideoClip([clip, *caption_clips]).with_audio(clip.audio)
        composed.write_videofile(
            str(config.output_path),
            fps=config.fps,
            codec="libx264",
            audio_codec="aac",
            preset=config.x264_preset,
        )
    finally:
        clip.close()
