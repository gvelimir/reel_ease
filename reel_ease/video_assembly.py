"""Crop and concatenate the selected scenes into a 9:16 base with one ffmpeg pass.

Each segment is pre-trimmed via input seeking (`-ss`/`-t`), scaled to cover the
target frame, center-cropped, and normalized (fps, SAR, pixel format) so the
`concat` filter can join them. This replaces per-frame moviepy processing, which
was the pipeline's main bottleneck.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

from reel_ease.config import ReelConfig
from reel_ease.ffmpeg_tools import ffmpeg_binary
from reel_ease.scene_detection import SceneSegment


def assemble_base_video(
    segments: list[SceneSegment],
    config: ReelConfig,
    output_path: Path,
    include_source_audio: bool,
) -> bool:
    """Write the concatenated 9:16 base video. Returns whether it carries audio.

    Source audio is only kept when requested AND every source has an audio
    stream — mixing present and absent streams in `concat` is not reliable, so
    we degrade to a silent base rather than fail.
    """
    use_audio = include_source_audio and all(
        _has_audio_stream(segment.video_path) for segment in segments
    )

    inputs: list[str] = []
    for segment in segments:
        inputs += [
            "-ss", f"{segment.start:.3f}",
            "-t", f"{segment.duration:.3f}",
            "-i", str(segment.video_path),
        ]

    filtergraph, stream_maps = _build_filtergraph(len(segments), config, use_audio)
    command = [
        ffmpeg_binary(), "-y",
        *inputs,
        "-filter_complex", filtergraph,
        *stream_maps,
        "-c:v", "libx264",
        "-preset", config.x264_preset,
        "-pix_fmt", "yuv420p",
    ]
    command += ["-c:a", "aac"] if use_audio else ["-an"]
    command += ["-loglevel", "error", str(output_path)]
    subprocess.run(command, check=True)
    return use_audio


def _build_filtergraph(
    segment_count: int, config: ReelConfig, use_audio: bool
) -> tuple[str, list[str]]:
    width, height, fps = config.width, config.height, config.fps
    # setpts=PTS-STARTPTS zeroes each segment's timeline: after input `-ss`
    # seeking the frames keep their original timestamps, which makes concat
    # mis-time the join and inflate the total duration.
    chains = [
        f"[{i}:v]setpts=PTS-STARTPTS,"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{i}]"
        for i in range(segment_count)
    ]

    if use_audio:
        chains += [
            f"[{i}:a]asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates=44100:channel_layouts=stereo[a{i}]"
            for i in range(segment_count)
        ]
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(segment_count))
        chains.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=1[vout][aout]")
        return ";".join(chains), ["-map", "[vout]", "-map", "[aout]"]

    concat_inputs = "".join(f"[v{i}]" for i in range(segment_count))
    chains.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=0[vout]")
    return ";".join(chains), ["-map", "[vout]"]


@functools.lru_cache(maxsize=None)
def _has_audio_stream(video_path: Path) -> bool:
    """Detect an audio stream via ffmpeg's stream dump (no ffprobe required)."""
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
    )
    return "Audio:" in result.stderr
