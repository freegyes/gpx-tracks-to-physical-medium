"""Border layer extraction and laser polygon building."""

from shapely.geometry import LineString, box
from shapely.ops import linemerge, unary_union

from .config import GenerationConfig
from .geometry import (
    CoordTransformer,
    collect_linestrings,
    collect_polygons,
    find_neighbors,
    mercator_lines_to_svg,
    project_and_clip_border,
    remove_orphan_geometries,
)


def extract_border_data(geojson, country_polys, country_union, transformer,
                        config: GenerationConfig):
    """Extract border lines, return SVG mm polylines."""
    print("Finding neighboring countries...")
    hb = country_union.bounds
    expand = 1.0
    search_box = box(hb[0] - expand, hb[1] - expand, hb[2] + expand, hb[3] + expand)
    neighbors = find_neighbors(geojson, country_union, search_box,
                               country_name=config.country)
    print(f"  Found neighbors: {', '.join(sorted(neighbors.keys()))}")

    clip_box = transformer.drawable_box_projected()

    print(f"Processing {config.country}'s border...")
    country_mercator = project_and_clip_border(country_polys, transformer, clip_box)
    print(f"  {config.country}: {len(country_mercator)} line segment(s)")

    print("Processing neighbor borders...")
    all_mercator = list(country_mercator)
    for name, polys in sorted(neighbors.items()):
        segs = project_and_clip_border(
            polys, transformer, clip_box, merge_and_filter=True
        )
        all_mercator.extend(segs)
        print(f"  {name}: {len(segs)} clipped segment(s)")

    print("Deduplicating shared borders...")
    merged = linemerge(unary_union(all_mercator))
    deduped = collect_linestrings(merged)
    print(f"  {len(all_mercator)} input segments -> {len(deduped)} unique segments")

    # --- Remove orphan border segments not connected to the country ---
    if country_mercator:
        print("Removing orphan borders...")
        seed = unary_union(country_mercator).buffer(500)
        result = remove_orphan_geometries(deduped, seed, tolerance=500)
        orphan_count = len(deduped) - len(result)
        print(f"  Borders after orphan removal: {len(result)} segment(s) ({orphan_count} orphan(s) removed)")
        deduped = result

    return mercator_lines_to_svg(deduped, transformer)


def build_border_laser_polys(svg_lines, config: GenerationConfig):
    """Buffer border SVG mm lines into filled polygons for laser engraving."""
    shapely_lines = [LineString(pts) for pts in svg_lines if len(pts) >= 2]
    half_w = config.fabrication.laser_border_width_mm / 2
    buffered = unary_union([
        line.buffer(half_w, cap_style="round", join_style="round")
        for line in shapely_lines
    ])
    clip_rect = box(config.draw_x_min, config.draw_y_min,
                    config.draw_x_max, config.draw_y_max)
    buffered = buffered.intersection(clip_rect)
    return collect_polygons(buffered)
