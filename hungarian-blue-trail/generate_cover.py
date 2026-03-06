#!/usr/bin/env python3
"""CLI wrapper: generates hiking trail notebook cover SVGs."""

import argparse
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so gpx2fab is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from gpx2fab.config import CaptionConfig, GenerationConfig, PageConfig
from gpx2fab.pipeline import generate

parser = argparse.ArgumentParser(description="Generate fabrication-ready SVGs from a GPX trail.")
parser.add_argument("--gpx", default="hungarian-blue-trail/input/okt_teljes_20260130.gpx",
                    help="Path to the input GPX file")
parser.add_argument("--output", default="hungarian-blue-trail/output",
                    help="Output directory for generated files")
parser.add_argument("--title", default="ORSZÁGOS KÉKTÚRA",
                    help="Caption title text")
parser.add_argument("--subtitle", default="1172 km",
                    help="Caption subtitle text")
parser.add_argument("--country", default="Hungary",
                    help="Country name (Natural Earth spelling, e.g. 'Hungary', 'Austria')")
parser.add_argument("--page-width", type=float, default=210,
                    help="Page width in mm (default: 210)")
parser.add_argument("--page-height", type=float, default=148,
                    help="Page height in mm (default: 148)")
parser.add_argument("--cache", default=".cache",
                    help="Cache directory for downloaded geodata (default: .cache)")
parser.add_argument("--no-plotter", action="store_true",
                    help="Skip plotter SVG output")
parser.add_argument("--no-laser", action="store_true",
                    help="Skip laser SVG output")
args = parser.parse_args()

TRAIL_GPX = Path(args.gpx)
OUTPUT_DIR = Path(args.output)
CACHE_DIR = Path(args.cache)

config = GenerationConfig(
    country=args.country,
    page=PageConfig(width_mm=args.page_width, height_mm=args.page_height),
    caption=CaptionConfig(title=args.title, subtitle=args.subtitle),
    output_plotter=not args.no_plotter,
    output_laser=not args.no_laser,
)

gpx_bytes = TRAIL_GPX.read_bytes()
result = generate(config, gpx_bytes, CACHE_DIR)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if result.plotter_svg:
    (OUTPUT_DIR / f"plotter_{args.page_width:.0f}x{args.page_height:.0f}mm.svg").write_bytes(result.plotter_svg)
if result.laser_svg:
    (OUTPUT_DIR / f"laser_{args.page_width:.0f}x{args.page_height:.0f}mm.svg").write_bytes(result.laser_svg)
(OUTPUT_DIR / "preview.png").write_bytes(result.preview_png)
