"""Orchestrator: config + GPX bytes -> GenerationResult."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import cairosvg
from shapely.geometry import box
from shapely.ops import unary_union

from .borders import build_border_laser_polys, extract_border_data
from .config import GenerationConfig
from .data import fetch_countries_geojson
from .geometry import (
    CoordTransformer,
    collect_polygons,
    country_to_svg_mm_polygon,
    find_country,
    project_polygon_to_mercator,
)
from .svg_laser import write_laser_svg
from .svg_plotter import write_plotter_svg
from .trail import build_trail_laser_polys, extract_trail
from .water import build_water_laser_polys, extract_water_features


@dataclass
class GenerationResult:
    plotter_svg: bytes | None
    laser_svg: bytes | None
    preview_png: bytes


def generate(config: GenerationConfig, gpx_data: bytes, cache_dir: Path) -> GenerationResult:
    """Takes config + raw GPX bytes, returns output file bytes (no disk I/O)."""
    print("=== GPX Tracks to Physical Medium ===\n")

    # --- Setup ---
    print("Loading country data...")
    geojson = fetch_countries_geojson(cache_dir)
    print(f"Extracting {config.country}...")
    country_polys = find_country(geojson, config.country)
    country_union = unary_union(country_polys)
    print(f"  {config.country}: {len(country_polys)} polygon(s)")
    print("Setting up coordinate transform...")
    transformer = CoordTransformer(country_union, config)
    clip_box = transformer.drawable_box_projected()
    country_mercator = project_polygon_to_mercator(country_polys, transformer)

    # --- Border ---
    print("\n--- Border ---")
    border_svg_lines = extract_border_data(geojson, country_polys, country_union,
                                           transformer, config)

    # --- Water ---
    print("\n--- Water ---")
    print("Extracting water features...")
    river_lines, lake_polys = extract_water_features(
        clip_box, transformer, config, cache_dir,
        country_mercator=country_mercator)

    # --- Trail ---
    print("\n--- Trail ---")
    print("Extracting trail from GPX...")
    trail_lines = extract_trail(gpx_data, clip_box, transformer)
    print(f"  Trail: {len(trail_lines)} segment(s)")

    print("Building country border inset...")
    country_mm = country_to_svg_mm_polygon(country_polys, transformer)
    country_inset = country_mm.buffer(-config.fabrication.laser_border_width_mm / 2)

    # --- Build laser polygon sets ---
    print("\n--- Building laser shapes ---")
    border_laser_polys = build_border_laser_polys(border_svg_lines, config)
    print(f"  Border: {len(border_laser_polys)} polygon(s)")
    water_laser_polys = build_water_laser_polys(river_lines, lake_polys, transformer, config)
    print(f"  Water: {len(water_laser_polys)} polygon(s)")
    trail_laser_polys = build_trail_laser_polys(
        trail_lines, transformer, config,
        lake_polys_mercator=lake_polys,
        country_inset_mm=country_inset)
    print(f"  Trail: {len(trail_laser_polys)} polygon(s)")

    # --- Combine border + water for engrave layer ---
    print("\n--- Combining engrave layer (borders + water) ---")
    engrave_union = unary_union(border_laser_polys + water_laser_polys)
    clip_rect = box(config.draw_x_min, config.draw_y_min,
                    config.draw_x_max, config.draw_y_max)
    engrave_clipped = engrave_union.intersection(clip_rect)
    engrave_polys = collect_polygons(engrave_clipped)
    print(f"  Combined engrave: {len(engrave_polys)} polygon(s)")

    # --- Generate output bytes ---
    print("\n--- Generating output files ---")

    plotter_svg = None
    if config.output_plotter:
        plotter_svg = write_plotter_svg(border_svg_lines, river_lines, lake_polys,
                                        trail_laser_polys, transformer, config)
        print(f"  Plotter SVG: {len(plotter_svg)} bytes")

    laser_svg = None
    if config.output_laser:
        laser_svg = write_laser_svg(engrave_polys, trail_laser_polys, config)
        print(f"  Laser SVG: {len(laser_svg)} bytes")

    # Preview PNG (render plotter SVG at screen resolution)
    preview_dpi = 150
    png_w = round(config.page.width_mm / 25.4 * preview_dpi)
    svg_for_preview = plotter_svg or laser_svg
    preview_png = cairosvg.svg2png(bytestring=svg_for_preview,
                                   output_width=png_w,
                                   background_color="white")
    print(f"  Preview PNG: {len(preview_png)} bytes ({png_w}px wide)")

    # --- Summary ---
    w = config.page.width_mm
    h = config.page.height_mm
    print(f"\n{'='*50}")
    print(f"  Dimensions: {w}mm x {h}mm")
    print(f"  Padding: {config.page.padding_mm}mm")
    if plotter_svg:
        print(f"  Plotter SVG: 4 layers")
    if laser_svg:
        print(f"  Laser SVG: 4 layers")
    print(f"{'='*50}")
    print("\nDone!")

    return GenerationResult(
        plotter_svg=plotter_svg,
        laser_svg=laser_svg,
        preview_png=preview_png,
    )
