"""Extract representative still frames from scene segments for vision ranking."""

from __future__ import annotations

import base64
import io

from PIL import Image

from reel_ease.scene_detection import SceneSegment

_PREVIEW_WIDTH = 512


def segment_frame_data_url(segment: SceneSegment) -> str:
    """A downscaled JPEG of the segment's midpoint frame as a data: URL.

    Downscaling keeps the OpenAI vision payload (and token cost) small — full
    resolution adds nothing to a highlight-worthiness judgement.
    """
    from moviepy import VideoFileClip

    with VideoFileClip(str(segment.video_path)) as clip:
        sample_time = min(segment.midpoint, max(clip.duration - 0.05, 0))
        frame = clip.get_frame(sample_time)

    image = Image.fromarray(frame)
    if image.width > _PREVIEW_WIDTH:
        ratio = _PREVIEW_WIDTH / image.width
        image = image.resize((_PREVIEW_WIDTH, int(image.height * ratio)))

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=80)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
