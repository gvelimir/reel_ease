#!/usr/bin/env python3
"""Convenience entrypoint: `python make_reel.py --videos ... --output reel.mp4`."""

from reel_ease.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
