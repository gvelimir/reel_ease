"""Turn provided caption lines into timed on-screen text clips."""

from __future__ import annotations

from moviepy import TextClip


def build_caption_clips(
    caption_lines: list[str],
    total_duration: float,
    width: int,
    height: int,
    font_path: str,
) -> list[TextClip]:
    """One caption per equal time slice of the reel, bottom-centered.

    Captions are spread evenly across the full duration rather than tied to
    clip boundaries, so the count of caption lines is independent of how many
    scenes were selected.
    """
    if not caption_lines:
        return []

    slice_duration = total_duration / len(caption_lines)
    font_size = max(int(height * 0.045), 28)
    box_width = int(width * 0.9)

    clips: list[TextClip] = []
    for index, line in enumerate(caption_lines):
        text_clip = (
            TextClip(
                text=line,
                font=font_path,
                font_size=font_size,
                color="white",
                stroke_color="black",
                stroke_width=max(font_size // 12, 2),
                method="caption",
                size=(box_width, None),
                text_align="center",
            )
            .with_start(index * slice_duration)
            .with_duration(slice_duration)
            .with_position(("center", int(height * 0.72)))
        )
        clips.append(text_clip)
    return clips
