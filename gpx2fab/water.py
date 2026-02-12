"""Water layer extraction and laser polygon building."""

from pathlib import Path

from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import linemerge, unary_union

from .config import GenerationConfig
from .data import NE_BASE_URL, WATER_SOURCES, fetch_geojson
from .geometry import (
    CoordTransformer,
    collect_linestrings,
    collect_polygons,
    mercator_to_svg_mm,
    remove_orphan_geometries,
)
from .svg_common import generate_hatch_lines


def extract_water_features(clip_box_projected, transformer: CoordTransformer,
                           config: GenerationConfig, cache_dir: Path,
                           country_mercator=None):
    """Download water GeoJSON files and return clipped river lines and lake polys
    in Mercator coordinates.

    If country_mercator is provided, orphan rivers (those not connected to
    the country's territory or to lakes/rivers that are) are removed.
    """
    print("  Downloading water data...")
    datasets = {}
    for key, filename in WATER_SOURCES.items():
        url = NE_BASE_URL + filename
        datasets[key] = fetch_geojson(url, filename, cache_dir)

    proj = transformer.proj

    # --- Rivers ---
    print("  Processing rivers...")
    all_river_lines = []
    for key in ("rivers_global", "rivers_europe"):
        for feat in datasets[key]["features"]:
            geom = shape(feat["geometry"])
            if geom.is_empty:
                continue
            lines = collect_linestrings(geom)
            for line in lines:
                projected_coords = [proj.transform(x, y) for x, y in line.coords]
                projected_line = LineString(projected_coords)
                if not projected_line.intersects(clip_box_projected):
                    continue
                clipped = projected_line.intersection(clip_box_projected)
                all_river_lines.extend(collect_linestrings(clipped))

    if all_river_lines:
        merged = linemerge(unary_union(all_river_lines))
        river_lines = collect_linestrings(merged)
    else:
        river_lines = []
    print(f"  Rivers: {len(river_lines)} segment(s)")

    # --- Lakes ---
    print("  Processing lakes...")
    all_lake_polys = []
    for key in ("lakes_global", "lakes_europe"):
        for feat in datasets[key]["features"]:
            geom = shape(feat["geometry"])
            if geom.is_empty:
                continue
            polys = collect_polygons(geom)
            for poly in polys:
                projected_ext = [proj.transform(x, y) for x, y in poly.exterior.coords]
                projected_holes = [
                    [proj.transform(x, y) for x, y in hole.coords]
                    for hole in poly.interiors
                ]
                projected_poly = Polygon(projected_ext, projected_holes)
                if not projected_poly.intersects(clip_box_projected):
                    continue
                clipped = projected_poly.intersection(clip_box_projected)
                all_lake_polys.extend(collect_polygons(clipped))

    if all_lake_polys:
        lake_union = unary_union(all_lake_polys)
        lake_polys = collect_polygons(lake_union)
    else:
        lake_polys = []
    print(f"  Lakes: {len(lake_polys)} polygon(s)")

    # --- Remove river segments inside lakes ---
    if river_lines and lake_polys:
        print("  Removing rivers inside lakes...")
        lakes_union = unary_union(lake_polys)
        trimmed = []
        for line in river_lines:
            diff = line.difference(lakes_union)
            trimmed.extend(collect_linestrings(diff))
        removed = len(river_lines) - len(trimmed)
        river_lines = trimmed
        print(f"  Rivers after lake subtraction: {len(river_lines)} segment(s) ({removed} removed/split)")

    # --- Remove orphan rivers not connected to country ---
    if country_mercator is not None and river_lines:
        print("  Removing orphan rivers...")
        touch_buf = 500  # meters in Mercator
        country_buf = country_mercator.buffer(touch_buf)
        seed_zone = country_buf
        if lake_polys:
            touching_lakes = [lp for lp in lake_polys if lp.intersects(country_buf)]
            if touching_lakes:
                seed_zone = unary_union([country_buf] + touching_lakes)

        result = remove_orphan_geometries(river_lines, seed_zone, tolerance=touch_buf)
        orphan_count = len(river_lines) - len(result)
        river_lines = result
        print(f"  Rivers after orphan removal: {len(river_lines)} segment(s) ({orphan_count} orphan(s) removed)")

    return river_lines, lake_polys


def build_water_laser_polys(river_lines, lake_polys, transformer: CoordTransformer,
                            config: GenerationConfig):
    """Build filled polygons for laser engraving of water features."""
    fab = config.fabrication
    all_shapes = []

    for line in river_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        if len(pts_mm) >= 2:
            svg_line = LineString(pts_mm)
            all_shapes.append(svg_line.buffer(fab.river_buffer_mm, cap_style="round", join_style="round"))

    for poly in lake_polys:
        ext_mm = mercator_to_svg_mm(poly.exterior.coords, transformer)
        holes_mm = [mercator_to_svg_mm(hole.coords, transformer) for hole in poly.interiors]
        lake_shape_mm = Polygon(ext_mm, holes_mm)
        outline = LineString(ext_mm)
        all_shapes.append(outline.buffer(fab.river_buffer_mm, cap_style="round", join_style="round"))
        for hole_mm in holes_mm:
            hole_line = LineString(hole_mm)
            all_shapes.append(hole_line.buffer(fab.river_buffer_mm, cap_style="round", join_style="round"))
        for hatch_line in generate_hatch_lines(lake_shape_mm, fab.hatch_spacing_mm, fab.hatch_angle_deg):
            all_shapes.append(hatch_line.buffer(fab.river_buffer_mm, cap_style="round", join_style="round"))

    if not all_shapes:
        return []

    water_union = unary_union(all_shapes)
    clip_rect = box(config.draw_x_min, config.draw_y_min,
                    config.draw_x_max, config.draw_y_max)
    water_clipped = water_union.intersection(clip_rect)
    return collect_polygons(water_clipped)
