"""Command-line entrypoint that wires arguments into a ReelConfig build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reel_ease.config import ReelConfig
from reel_ease.reel_builder import build_reel


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reel_ease",
        description="Build a vertical highlight reel with captions and music.",
    )
    parser.add_argument(
        "--videos", nargs="+", required=True, help="Input video file(s), in order."
    )
    parser.add_argument("--output", default="reel.mp4", help="Output .mp4 path.")
    parser.add_argument(
        "--captions", help="Text file, one caption line per row (exact overlay text)."
    )
    parser.add_argument("--music-url", help="YouTube URL for the soundtrack.")
    parser.add_argument(
        "--music-file", help="Local audio file for the soundtrack (skips download)."
    )

    parser.add_argument("--duration", type=float, default=30.0, help="Target seconds.")
    parser.add_argument("--max-clip", type=float, default=4.0, help="Max seconds/clip.")
    parser.add_argument("--min-scene", type=float, default=1.0, help="Min scene seconds.")
    parser.add_argument(
        "--scene-threshold", type=float, default=27.0, help="scenedetect sensitivity."
    )
    parser.add_argument(
        "--scene-frame-skip",
        type=int,
        default=2,
        help="Sample every (skip+1)th frame during detection (higher = faster).",
    )
    parser.add_argument(
        "--scene-downscale",
        type=int,
        default=None,
        help="Downscale factor before detection (default: auto).",
    )
    parser.add_argument(
        "--scene-workers",
        type=int,
        default=None,
        help="Parallel detection processes (default: one per video, cpu-capped).",
    )

    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="x264 encode preset (ultrafast..veryslow). Faster = larger file.",
    )

    parser.add_argument(
        "--no-ai", action="store_true", help="Skip OpenAI ranking (heuristic only)."
    )
    parser.add_argument("--openai-model", default=None, help="Vision model override.")
    parser.add_argument("--font", help="Path to a .ttf font for captions.")
    parser.add_argument(
        "--caption-backend",
        choices=("ffmpeg", "moviepy"),
        default="ffmpeg",
        help="ffmpeg=fast native drawtext (default); moviepy=per-frame overlay.",
    )

    parser.add_argument(
        "--keep-original-audio",
        action="store_true",
        help="Mix the source audio under the music instead of replacing it.",
    )
    parser.add_argument("--music-volume", type=float, default=1.0)
    parser.add_argument("--original-volume", type=float, default=0.25)
    parser.add_argument(
        "--music-start",
        type=float,
        default=None,
        help="Seconds into the track to start (default: the URL's t= param).",
    )
    parser.add_argument(
        "--cookies", help="Path to a cookies.txt for YouTube (bypasses bot check)."
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser to read YouTube cookies from, e.g. firefox, chrome.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = ReelConfig(
        video_paths=[Path(video) for video in args.videos],
        output_path=Path(args.output),
        caption_file=Path(args.captions) if args.captions else None,
        youtube_url=args.music_url,
        music_file=Path(args.music_file) if args.music_file else None,
        target_duration=args.duration,
        max_clip_seconds=args.max_clip,
        min_scene_seconds=args.min_scene,
        scene_threshold=args.scene_threshold,
        scene_frame_skip=args.scene_frame_skip,
        scene_downscale=args.scene_downscale,
        scene_workers=args.scene_workers,

        width=args.width,
        height=args.height,
        fps=args.fps,
        x264_preset=args.preset,
        use_ai=not args.no_ai,
        font_path=args.font,
        caption_backend=args.caption_backend,
        keep_original_audio=args.keep_original_audio,
        music_volume=args.music_volume,
        original_audio_volume=args.original_volume,
        music_start=args.music_start,
        cookies_file=Path(args.cookies) if args.cookies else None,
        cookies_from_browser=args.cookies_from_browser,
    )
    if args.openai_model:
        config.openai_model = args.openai_model

    try:
        selection = build_reel(config)
    except Exception as error:  # noqa: BLE001 - surface a clean message to the CLI
        print(f"reel_ease failed: {error}", file=sys.stderr)
        return 1

    print(f"\nHighlight summary: {selection.summary}")
    print(f"Scenes used: {len(selection.segments)}")
    print(f"Wrote reel: {config.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
