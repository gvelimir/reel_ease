"""reel_ease — build a vertical highlight reel from source videos.

Pipeline: scene-detect candidate segments -> rank them with OpenAI vision ->
crop to 9:16 -> overlay caption lines -> lay a YouTube music track underneath.
"""

__all__ = ["ReelConfig", "build_reel"]

from reel_ease.config import ReelConfig
from reel_ease.reel_builder import build_reel
