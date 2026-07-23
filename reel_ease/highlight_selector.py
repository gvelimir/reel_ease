"""Rank scene segments into a highlight ordering using OpenAI vision."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from reel_ease.frames import segment_frame_data_url
from reel_ease.scene_detection import SceneSegment

_SYSTEM_PROMPT = (
    "You are a video editor assembling a short vertical highlight reel. "
    "You are shown one representative frame per candidate scene. Judge each "
    "scene's highlight-worthiness: visual interest, action, emotion, clarity, "
    "and variety across the final selection. Prefer a diverse, engaging cut."
)


@dataclass
class HighlightSelection:
    """The chosen segments in play order plus a human-readable summary."""

    segments: list[SceneSegment]
    summary: str


def select_highlights(
    segments: list[SceneSegment],
    target_duration: float,
    max_clip_seconds: float,
    use_ai: bool,
    model: str,
) -> HighlightSelection:
    """Pick and order the segments that fill target_duration.

    Uses OpenAI vision when enabled and a key is present; otherwise (or on any
    API failure) falls back to a deterministic longest-first heuristic.
    """
    if use_ai and os.environ.get("OPENAI_API_KEY"):
        try:
            ordered, summary = _rank_with_openai(segments, model)
            return _fill_to_duration(ordered, summary, target_duration, max_clip_seconds)
        except Exception as error:  # noqa: BLE001 - degrade gracefully, never crash
            fallback_note = f"(OpenAI ranking unavailable: {error}) "
            return _heuristic_selection(segments, target_duration, max_clip_seconds, fallback_note)

    return _heuristic_selection(segments, target_duration, max_clip_seconds, "")


def _rank_with_openai(
    segments: list[SceneSegment], model: str
) -> tuple[list[SceneSegment], str]:
    from openai import OpenAI

    client = OpenAI()
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"There are {len(segments)} candidate scenes, indexed 0.."
                f"{len(segments) - 1}. Return JSON: "
                '{"summary": str, "ranking": [int, ...]} where ranking lists '
                "scene indices best-first. summary is 1-2 sentences describing "
                "the highlights you chose."
            ),
        }
    ]
    for index, segment in enumerate(segments):
        content.append({"type": "text", "text": f"Scene {index}:"})
        content.append(
            {"type": "image_url", "image_url": {"url": segment_frame_data_url(segment)}}
        )

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )
    parsed = json.loads(response.choices[0].message.content)
    ranking = [i for i in parsed.get("ranking", []) if 0 <= i < len(segments)]
    # Append any indices the model omitted so nothing is silently dropped.
    ranking += [i for i in range(len(segments)) if i not in ranking]
    ordered = [segments[i] for i in ranking]
    summary = parsed.get("summary", "").strip() or "Highlights selected by OpenAI."
    return ordered, summary


def _fill_to_duration(
    ordered: list[SceneSegment],
    summary: str,
    target_duration: float,
    max_clip_seconds: float,
) -> HighlightSelection:
    """Take best-ranked segments until the reel reaches target_duration."""
    chosen: list[SceneSegment] = []
    total = 0.0
    for segment in ordered:
        chosen.append(segment)
        total += min(segment.duration, max_clip_seconds)
        if total >= target_duration:
            break
    return HighlightSelection(chosen, summary)


def _heuristic_selection(
    segments: list[SceneSegment],
    target_duration: float,
    max_clip_seconds: float,
    note: str,
) -> HighlightSelection:
    """Deterministic fallback: longest scenes first, kept in source order."""
    ranked = sorted(segments, key=lambda s: s.duration, reverse=True)
    filled = _fill_to_duration(ranked, "", target_duration, max_clip_seconds)
    in_source_order = sorted(
        filled.segments, key=lambda s: (str(s.video_path), s.start)
    )
    summary = (
        note
        + f"Selected {len(in_source_order)} scenes by length to fill "
        f"~{target_duration:.0f}s."
    )
    return HighlightSelection(in_source_order, summary)
