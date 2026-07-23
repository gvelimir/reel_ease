"""Locate the ffmpeg binary, preferring a system install over the bundled one."""

from __future__ import annotations

import functools
import shutil


@functools.lru_cache(maxsize=1)
def ffmpeg_binary() -> str:
    """Path to an ffmpeg executable.

    Prefers a system ffmpeg on PATH; otherwise falls back to the static binary
    that moviepy's imageio-ffmpeg dependency ships, so nothing extra needs
    installing.
    """
    system = shutil.which("ffmpeg")
    if system:
        return system
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()
