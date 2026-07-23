"""Burn captions with native ffmpeg filters — fast, one render per caption.

Prefers the `drawtext` filter when the ffmpeg build supports it. Many static
builds (including the bundled imageio-ffmpeg one) omit drawtext/freetype, so we
fall back to rendering each caption to a PNG with Pillow and compositing them
with the always-available `overlay` filter. Either way text is rasterized once,
not per frame, unlike the moviepy TextClip path.
"""

from __future__ import annotations

import functools
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reel_ease.ffmpeg_tools import ffmpeg_binary

_CAPTION_Y_FRACTION = 0.72


def burn_captions(
    input_video: Path,
    output_video: Path,
    caption_lines: list[str],
    total_duration: float,
    width: int,
    height: int,
    font_path: str,
    preset: str = "veryfast",
) -> None:
    """Overlay caption_lines (one per equal time slice) and write output_video."""
    slice_duration = total_duration / len(caption_lines)
    windows = [
        (index * slice_duration, (index + 1) * slice_duration)
        for index in range(len(caption_lines))
    ]
    font_size = max(int(height * 0.045), 28)
    border_width = max(font_size // 12, 2)
    y_position = int(height * _CAPTION_Y_FRACTION)
    work_dir = Path(tempfile.mkdtemp(prefix="reel_ease_caps_"))

    if _ffmpeg_has_drawtext():
        command = _drawtext_command(
            input_video, output_video, caption_lines, windows, width, height,
            font_size, border_width, y_position, font_path, work_dir, preset,
        )
    else:
        command = _overlay_command(
            input_video, output_video, caption_lines, windows, width,
            font_size, border_width, y_position, font_path, work_dir, preset,
        )
    subprocess.run(command, check=True)


@functools.lru_cache(maxsize=1)
def _ffmpeg_has_drawtext() -> bool:
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
    )
    return "drawtext" in result.stdout


def _wrapped(line: str, width: int, font_size: int) -> str:
    approx_chars = max(int((width * 0.9) / (font_size * 0.6)), 8)
    return textwrap.fill(line, width=approx_chars)


# --- overlay backend (PNG per caption) -------------------------------------

def _overlay_command(
    input_video: Path,
    output_video: Path,
    caption_lines: list[str],
    windows: list[tuple[float, float]],
    width: int,
    font_size: int,
    border_width: int,
    y_position: int,
    font_path: str,
    work_dir: Path,
    preset: str,
) -> list[str]:
    font = ImageFont.truetype(font_path, font_size)
    png_paths = [
        _render_caption_png(line, index, width, font, border_width, work_dir)
        for index, line in enumerate(caption_lines)
    ]

    inputs = [ffmpeg_binary(), "-y", "-i", str(input_video)]
    for png_path in png_paths:
        inputs += ["-i", str(png_path)]

    chains = []
    previous = "[0:v]"
    for index, (start, end) in enumerate(windows):
        label = "[vout]" if index == len(windows) - 1 else f"[v{index}]"
        chains.append(
            f"{previous}[{index + 1}:v]overlay=x=(W-w)/2:y={y_position}:"
            f"enable='between(t,{start:.3f},{end:.3f})'{label}"
        )
        previous = label

    return inputs + [
        "-filter_complex", ";".join(chains),
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(output_video),
    ]


def _render_caption_png(
    line: str,
    index: int,
    width: int,
    font: ImageFont.FreeTypeFont,
    border_width: int,
    work_dir: Path,
) -> Path:
    """Render one caption to a transparent PNG sized to the frame width."""
    text = _wrapped(line, width, font.size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = measure.multiline_textbbox(
        (0, 0), text, font=font, stroke_width=border_width, align="center"
    )
    pad = border_width + 4
    image = Image.new(
        "RGBA",
        (int(box[2] - box[0]) + 2 * pad, int(box[3] - box[1]) + 2 * pad),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(image).multiline_text(
        (pad - int(box[0]), pad - int(box[1])),
        text,
        font=font,
        fill="white",
        stroke_width=border_width,
        stroke_fill="black",
        align="center",
    )
    png_path = work_dir / f"caption_{index}.png"
    image.save(png_path)
    return png_path


# --- drawtext backend (used when the ffmpeg build supports it) -------------

def _drawtext_command(
    input_video: Path,
    output_video: Path,
    caption_lines: list[str],
    windows: list[tuple[float, float]],
    width: int,
    height: int,
    font_size: int,
    border_width: int,
    y_position: int,
    font_path: str,
    work_dir: Path,
    preset: str,
) -> list[str]:
    filters = []
    for index, (line, (start, end)) in enumerate(zip(caption_lines, windows)):
        caption_file = work_dir / f"caption_{index}.txt"
        caption_file.write_text(_wrapped(line, width, font_size), encoding="utf-8")
        options = [
            f"fontfile='{_escape(font_path)}'",
            f"textfile='{_escape(str(caption_file))}'",
            "expansion=none",
            "fontcolor=white",
            f"fontsize={font_size}",
            f"borderw={border_width}",
            "bordercolor=black",
            "line_spacing=8",
            "x=(w-text_w)/2",
            f"y={y_position}",
            f"enable='between(t,{start:.3f},{end:.3f})'",
        ]
        filters.append("drawtext=" + ":".join(options))

    return [
        ffmpeg_binary(), "-y", "-i", str(input_video),
        "-vf", ",".join(filters),
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(output_video),
    ]


def _escape(path: str) -> str:
    """Escape characters special inside an ffmpeg filtergraph value."""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
