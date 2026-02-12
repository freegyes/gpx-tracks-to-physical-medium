#!/usr/bin/env python3
"""CLI wrapper: generates Hungarian Blue Trail notebook cover SVGs."""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so gpx2fab is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from gpx2fab.config import CaptionConfig, GenerationConfig
from gpx2fab.pipeline import generate

TRAIL_GPX = Path("hungarian-blue-trail/input/okt_teljes_20260130.gpx")
OUTPUT_DIR = Path("hungarian-blue-trail/output")
CACHE_DIR = Path(".cache")

config = GenerationConfig(
    country="Hungary",
    caption=CaptionConfig(title="ORSZÁGOS KÉKTÚRA", subtitle="1172 km"),
)

gpx_bytes = TRAIL_GPX.read_bytes()
result = generate(config, gpx_bytes, CACHE_DIR)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if result.plotter_svg:
    (OUTPUT_DIR / "plotter_210x148mm.svg").write_bytes(result.plotter_svg)
if result.laser_svg:
    (OUTPUT_DIR / "laser_210x148mm.svg").write_bytes(result.laser_svg)
(OUTPUT_DIR / "preview.png").write_bytes(result.preview_png)
