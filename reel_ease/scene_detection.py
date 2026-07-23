"""Find candidate highlight segments in each source video via scene cuts.

Detection is the pipeline's slowest stage, so it is sped up two ways: each
video is detected in its own process (lossless — independent files), and within
a video `frame_skip` samples fewer frames and `downscale` shrinks them before
the content comparison. Neither affects the returned timecodes, only precision.
"""

from __future__ import annotations

import functools
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from scenedetect import ContentDetector, SceneManager, open_video


@dataclass
class SceneSegment:
    """A time window inside one source video that may become a reel clip."""

    video_path: Path
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2


def detect_segments(
    video_path: Path,
    threshold: float,
    min_scene_seconds: float,
    max_clip_seconds: float,
    frame_skip: int = 0,
    downscale: int | None = None,
) -> list[SceneSegment]:
    """Detect scene-cut segments, trimmed to at most max_clip_seconds each.

    Falls back to fixed-length chunks when the detector finds no cuts (e.g. a
    single continuous shot), so we always return something usable.
    """
    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    if downscale is not None:
        scene_manager.auto_downscale = False
        scene_manager.downscale = downscale
    scene_manager.detect_scenes(video, frame_skip=frame_skip, show_progress=False)
    scenes = scene_manager.get_scene_list()

    segments: list[SceneSegment] = []
    for start_tc, end_tc in scenes:
        start = start_tc.get_seconds()
        end = end_tc.get_seconds()
        if end - start < min_scene_seconds:
            continue
        clipped_end = min(end, start + max_clip_seconds)
        segments.append(SceneSegment(video_path, start, clipped_end))

    if not segments:
        segments = _chunk_fallback(video_path, max_clip_seconds)
    return segments


def _chunk_fallback(video_path: Path, chunk_seconds: float) -> list[SceneSegment]:
    """Split a video into fixed windows when no scene cuts are detected."""
    from moviepy import VideoFileClip

    with VideoFileClip(str(video_path)) as clip:
        total = clip.duration
    segments: list[SceneSegment] = []
    start = 0.0
    while start < total:
        segments.append(
            SceneSegment(video_path, start, min(start + chunk_seconds, total))
        )
        start += chunk_seconds
    return segments


def detect_all_segments(
    video_paths: list[Path],
    threshold: float,
    min_scene_seconds: float,
    max_clip_seconds: float,
    frame_skip: int = 0,
    downscale: int | None = None,
    workers: int | None = None,
) -> list[SceneSegment]:
    """Detect segments across every input video, one process per video."""
    detect_one = functools.partial(
        detect_segments,
        threshold=threshold,
        min_scene_seconds=min_scene_seconds,
        max_clip_seconds=max_clip_seconds,
        frame_skip=frame_skip,
        downscale=downscale,
    )

    worker_count = workers or min(len(video_paths), os.cpu_count() or 1)
    if len(video_paths) <= 1 or worker_count <= 1:
        per_video = [detect_one(path) for path in video_paths]
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            per_video = list(executor.map(detect_one, video_paths))

    return [segment for segments in per_video for segment in segments]
