"""Download a YouTube track and mux it under the reel with ffmpeg.

Muxing uses `-c:v copy`, so adding music never re-encodes the video — only the
audio stream is built (loop-to-length, fade out, volume, optional mix with the
kept source audio).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from reel_ease.config import ReelConfig
from reel_ease.ffmpeg_tools import ffmpeg_binary


def download_youtube_audio(
    youtube_url: str,
    work_dir: Path,
    cookies_file: Path | None = None,
    cookies_from_browser: str | None = None,
) -> Path:
    """Download bestaudio from a YouTube URL and return the extracted mp3.

    Uses a system ffmpeg when present, else the bundled imageio-ffmpeg binary.
    YouTube often rejects anonymous/server downloads ("confirm you're not a
    bot") — pass cookies_file or cookies_from_browser to authenticate.
    Downloading is subject to YouTube's Terms of Service — use tracks you have
    the right to.
    """
    import yt_dlp

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "music.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_binary(),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if cookies_file:
        options["cookiefile"] = str(cookies_file)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)

    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([youtube_url])

    music_path = work_dir / "music.mp3"
    if not music_path.is_file():
        raise RuntimeError(f"Audio extraction produced no file for: {youtube_url}")
    return music_path


def add_music(
    video_path: Path,
    output_path: Path,
    config: ReelConfig,
    duration: float,
    source_audio_present: bool,
) -> None:
    """Lay the YouTube track under video_path, optionally mixing source audio."""
    if config.music_file:
        music_path = config.music_file
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="reel_ease_music_"))
        music_path = download_youtube_audio(
            config.youtube_url,
            work_dir,
            cookies_file=config.cookies_file,
            cookies_from_browser=config.cookies_from_browser,
        )

    if config.music_start is not None:
        start = config.music_start
    elif config.youtube_url:
        start = start_seconds_from_url(config.youtube_url)
    else:
        start = 0.0

    mix_original = source_audio_present and config.keep_original_audio
    if mix_original:
        filtergraph = (
            f"[0:a]volume={config.original_audio_volume}[original];"
            + _music_filter(start, duration, config.music_volume, "[music]")
            + ";[original][music]amix=inputs=2:duration=first:"
            "dropout_transition=0[aout]"
        )
    else:
        filtergraph = _music_filter(start, duration, config.music_volume, "[aout]")

    command = [
        ffmpeg_binary(), "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex", filtergraph,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        "-loglevel", "error",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def _music_filter(
    start: float, duration: float, volume: float, out_label: str
) -> str:
    """Trim the looped track to [start, start+duration], fade out, scale volume."""
    fade = min(2.0, duration / 4)
    return (
        f"[1:a]atrim={start:.3f}:{start + duration:.3f},asetpts=N/SR/TB,"
        f"afade=t=out:st={max(duration - fade, 0):.3f}:d={fade:.3f},"
        f"volume={volume}{out_label}"
    )


def start_seconds_from_url(url: str) -> float:
    """Read a YouTube start time (t= or start=) as seconds.

    Handles plain seconds ("94", "94s") and the h/m/s form ("1m34s", "1h2m3s").
    """
    query = parse_qs(urlparse(url).query)
    for key in ("t", "start"):
        if key in query:
            return _parse_timecode(query[key][0])
    return 0.0


def _parse_timecode(value: str) -> float:
    value = value.strip()
    if value.isdigit():
        return float(value)
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(group or 0) for group in match.groups())
        return float(hours * 3600 + minutes * 60 + seconds)
    return 0.0
