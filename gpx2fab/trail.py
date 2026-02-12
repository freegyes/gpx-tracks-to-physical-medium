"""Trail layer: GPX parsing, extraction, and laser polygon building."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import gpxpy
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .config import GenerationConfig
from .geometry import (
    CoordTransformer,
    collect_linestrings,
    collect_polygons,
    mercator_to_svg_mm,
)


def parse_gpx(source: bytes | Path) -> list[tuple[float, float]]:
    """Parse a GPX file and return a list of (lon, lat) tuples.

    Accepts raw bytes or a file Path.
    """
    if isinstance(source, (bytes, bytearray)):
        gpx = gpxpy.parse(BytesIO(source))
    else:
        with open(source, "r") as f:
            gpx = gpxpy.parse(f)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append((pt.longitude, pt.latitude))
    for route in gpx.routes:
        for pt in route.points:
            points.append((pt.longitude, pt.latitude))
    return points


def extract_trail(gpx_data: bytes | Path, clip_box_projected,
                  transformer: CoordTransformer) -> list[LineString]:
    """Parse GPX, project to Mercator, clip, return list of LineStrings."""
    points = parse_gpx(gpx_data)
    if len(points) < 2:
        return []
    projected = [transformer.proj.transform(lon, lat) for lon, lat in points]
    line = LineString(projected)
    clipped = line.intersection(clip_box_projected)
    return collect_linestrings(clipped)


def build_trail_laser_polys(trail_lines, transformer: CoordTransformer,
                            config: GenerationConfig,
                            lake_polys_mercator=None,
                            country_inset_mm=None):
    """Build filled polygons for laser cutting of trail.

    Subtracts lakes and clips to country's inset border.
    """
    half_w = config.trail_cut_width_mm / 2
    all_shapes = []
    for line in trail_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        if len(pts_mm) >= 2:
            svg_line = LineString(pts_mm)
            all_shapes.append(svg_line.buffer(half_w, cap_style="round", join_style="round"))

    if not all_shapes:
        return []

    trail_union = unary_union(all_shapes)
    clip_rect = box(config.draw_x_min, config.draw_y_min,
                    config.draw_x_max, config.draw_y_max)
    trail_clipped = trail_union.intersection(clip_rect)

    if country_inset_mm is not None:
        trail_clipped = trail_clipped.intersection(country_inset_mm)
        print(f"  Clipped trail to inside of border (inset {config.fabrication.laser_border_width_mm / 2}mm)")

    if lake_polys_mercator:
        lake_shapes_mm = []
        for poly in lake_polys_mercator:
            ext_mm = mercator_to_svg_mm(poly.exterior.coords, transformer)
            holes_mm = [mercator_to_svg_mm(h.coords, transformer) for h in poly.interiors]
            lake_shapes_mm.append(Polygon(ext_mm, holes_mm))
        lakes_union_mm = unary_union(lake_shapes_mm)
        trail_clipped = trail_clipped.difference(lakes_union_mm)
        print(f"  Subtracted {len(lake_polys_mercator)} lake polygon(s) from trail cutout")

    return collect_polygons(trail_clipped)
