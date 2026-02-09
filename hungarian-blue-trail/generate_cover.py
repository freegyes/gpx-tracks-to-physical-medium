#!/usr/bin/env python3
"""Generate an A5 landscape notebook cover SVG showing Hungary's border
centered, with neighboring country border fragments extending to the edges,
a water layer (rivers + lakes), and a trail layer (OKT hiking trail from GPX).

Outputs two vendor-ready SVGs into hungarian-blue-trail/output/:
  - plotter_210x148mm.svg  — 3 AxiDraw-compatible Inkscape layers (strokes only)
  - laser_210x148mm.svg    — 2 Inkscape layers: Engrave (black fill) + Cut (red hairline)

Usage:
    python3 hungarian-blue-trail/generate_cover.py
"""

import json
import shutil
from pathlib import Path

import cairosvg
import gpxpy
import requests
import svgwrite
from pyproj import Transformer
from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import linemerge, unary_union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DPI = 96
MM_TO_PX = DPI / 25.4  # 1 mm ≈ 3.7795 px

# A5 landscape dimensions
WIDTH_MM = 210
HEIGHT_MM = 148
PADDING_MM = 15

# Drawable area
DRAW_X_MIN = PADDING_MM
DRAW_Y_MIN = PADDING_MM
DRAW_X_MAX = WIDTH_MM - PADDING_MM   # 195
DRAW_Y_MAX = HEIGHT_MM - PADDING_MM  # 133
DRAW_W = DRAW_X_MAX - DRAW_X_MIN     # 180
DRAW_H = DRAW_Y_MAX - DRAW_Y_MIN     # 118

BORDER_STROKE_MM = 1.0

NE_BASE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/"
)
NATURAL_EARTH_URL = NE_BASE_URL + "ne_10m_admin_0_countries.geojson"

CACHE_DIR = Path(".cache")

# Output directory
OUTPUT_DIR = Path("hungarian-blue-trail/output")
DIMS = f"{WIDTH_MM}x{HEIGHT_MM}mm"
PLOTTER_FILE = OUTPUT_DIR / f"plotter_{DIMS}.svg"
LASER_FILE = OUTPUT_DIR / f"laser_{DIMS}.svg"
PREVIEW_FILE = OUTPUT_DIR / "preview.png"
PREVIEW_DPI = 150

# GPX input
TRAIL_GPX = Path("hungarian-blue-trail/input/okt_teljes_20260130.gpx")

# Stroke/buffer widths
LASER_BORDER_WIDTH_MM = 1.0  # engraved border width, matching a 1mm pen tip
WATER_STROKE_MM = 0.1  # thin stroke for plotter water features
RIVER_BUFFER_MM = 0.15  # buffer width for laser river engraving
HATCH_SPACING_MM = 0.5  # distance between hatching lines inside lakes
HATCH_ANGLE_DEG = 45  # hatching line angle
TRAIL_STROKE_MM = 0.1
TRAIL_CUT_WIDTH_MM = 1.5
LASER_HAIRLINE_MM = 0.01  # thin stroke for laser vector cut paths
LASER_CUT_COLOR = "#FF0000"      # red = vector cut
LASER_ENGRAVE_COLOR = "#000000"   # black = raster engrave

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_geojson(url: str, cache_name: str) -> dict:
    """Download a GeoJSON file from a URL, with local caching."""
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists():
        print(f"  Using cached: {cache_path}")
        with open(cache_path, "r") as f:
            return json.load(f)

    print(f"  Downloading {cache_name}...")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    with open(cache_path, "w") as f:
        json.dump(data, f)
    print(f"  Cached to {cache_path}")
    return data


def fetch_countries_geojson() -> dict:
    """Download Natural Earth 10m countries GeoJSON, with local caching."""
    return fetch_geojson(NATURAL_EARTH_URL, "ne_10m_admin_0_countries.geojson")


# ---------------------------------------------------------------------------
# Geometry extraction
# ---------------------------------------------------------------------------


def feature_to_polygons(feature) -> list[Polygon]:
    """Extract a list of Polygon objects from a GeoJSON feature."""
    geom = feature["geometry"]
    if geom["type"] == "Polygon":
        return [Polygon(geom["coordinates"][0],
                        [ring for ring in geom["coordinates"][1:]])]
    elif geom["type"] == "MultiPolygon":
        polys = []
        for poly_coords in geom["coordinates"]:
            polys.append(Polygon(poly_coords[0],
                                 [ring for ring in poly_coords[1:]]))
        return polys
    return []


def find_country(geojson: dict, name: str) -> list[Polygon]:
    """Find a country by NAME and return its polygons."""
    for feat in geojson["features"]:
        props = feat.get("properties", {})
        if props.get("NAME") == name or props.get("ADMIN") == name:
            polys = feature_to_polygons(feat)
            if polys:
                return polys
    raise ValueError(f"Country '{name}' not found in dataset")


def find_neighbors(geojson: dict, hungary_union, search_box) -> dict[str, list[Polygon]]:
    """Find all countries whose geometry intersects the expanded search box,
    excluding Hungary itself."""
    neighbors = {}
    for feat in geojson["features"]:
        props = feat.get("properties", {})
        name = props.get("NAME", "")
        if name == "Hungary":
            continue
        polys = feature_to_polygons(feat)
        if not polys:
            continue
        country_union = unary_union(polys)
        if country_union.intersects(search_box):
            neighbors[name] = polys
    return neighbors


# ---------------------------------------------------------------------------
# Coordinate transformation (WGS84 → Mercator → SVG mm)
# ---------------------------------------------------------------------------


class CoordTransformer:
    """WGS84 → Web Mercator → SVG mm coordinates, fitted to Hungary's bounds."""

    def __init__(self, hungary_union):
        self.proj = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

        # Project Hungary's bounding box
        minx, miny, maxx, maxy = hungary_union.bounds  # lon/lat
        x_min, y_min = self.proj.transform(minx, miny)
        x_max, y_max = self.proj.transform(maxx, maxy)

        # Uniform scale (fit-contain), reduced slightly so neighbor borders
        # have room to extend beyond Hungary on the tight-fitting axis
        INSET = 0.92  # Hungary fills 92% of drawable area, leaving ~4% margin each side
        sx = DRAW_W / (x_max - x_min)
        sy = DRAW_H / (y_max - y_min)
        self.scale = min(sx, sy) * INSET

        # Center offset
        projected_w = (x_max - x_min) * self.scale
        projected_h = (y_max - y_min) * self.scale
        self.offset_x = DRAW_X_MIN + (DRAW_W - projected_w) / 2
        self.offset_y = DRAW_Y_MIN + (DRAW_H - projected_h) / 2

        self.x_min = x_min
        self.y_max = y_max

    def transform(self, lon: float, lat: float) -> tuple[float, float]:
        """Convert WGS84 (lon, lat) to SVG mm coordinates."""
        x, y = self.proj.transform(lon, lat)
        svg_x = (x - self.x_min) * self.scale + self.offset_x
        svg_y = (self.y_max - y) * self.scale + self.offset_y  # Y flipped
        return round(svg_x, 4), round(svg_y, 4)

    def drawable_box_projected(self):
        """Return the drawable bounding box in projected (Mercator) coordinates."""
        x_min_m = (DRAW_X_MIN - self.offset_x) / self.scale + self.x_min
        x_max_m = (DRAW_X_MAX - self.offset_x) / self.scale + self.x_min
        y_max_m = self.y_max - (DRAW_Y_MIN - self.offset_y) / self.scale
        y_min_m = self.y_max - (DRAW_Y_MAX - self.offset_y) / self.scale
        return box(x_min_m, y_min_m, x_max_m, y_max_m)


# ---------------------------------------------------------------------------
# Geometry → SVG paths
# ---------------------------------------------------------------------------


def project_and_clip_border(
    polygons: list[Polygon],
    transformer: CoordTransformer,
    clip_box_projected,
    merge_and_filter: bool = False,
) -> list[LineString]:
    """Project polygon exterior rings to Mercator, clip to bounding box.

    Returns a list of Shapely LineStrings in Mercator coordinates.
    If merge_and_filter is True, connected segments are merged and only
    the longest continuous line is kept (drops small disconnected fragments).
    """
    clipped_geoms = []
    for poly in polygons:
        coords = list(poly.exterior.coords)
        if len(coords) < 2:
            continue
        projected = [transformer.proj.transform(lon, lat) for lon, lat in coords]
        try:
            line = LineString(projected)
        except Exception:
            continue

        clipped = line.intersection(clip_box_projected)
        if clipped.is_empty:
            continue

        if clipped.geom_type == "LineString":
            clipped_geoms.append(clipped)
        elif clipped.geom_type == "MultiLineString":
            clipped_geoms.extend(clipped.geoms)
        elif clipped.geom_type == "GeometryCollection":
            clipped_geoms.extend(
                g for g in clipped.geoms if g.geom_type == "LineString"
            )

    if merge_and_filter and len(clipped_geoms) > 1:
        merged = linemerge(clipped_geoms)
        if merged.geom_type == "LineString":
            clipped_geoms = [merged]
        elif merged.geom_type == "MultiLineString":
            segments = sorted(merged.geoms, key=lambda g: g.length, reverse=True)
            clipped_geoms = [segments[0]]

    return [g for g in clipped_geoms if not g.is_empty and len(g.coords) >= 2]


def mercator_lines_to_svg(
    mercator_geoms: list[LineString],
    transformer: CoordTransformer,
) -> list[list[tuple[float, float]]]:
    """Convert Mercator LineStrings to SVG mm coordinate lists."""
    result = []
    for g in mercator_geoms:
        svg_pts = []
        for mx, my in g.coords:
            svg_x = (mx - transformer.x_min) * transformer.scale + transformer.offset_x
            svg_y = (transformer.y_max - my) * transformer.scale + transformer.offset_y
            svg_pts.append((round(svg_x, 4), round(svg_y, 4)))
        result.append(svg_pts)
    return result


def mercator_to_svg_mm(coords, transformer):
    """Convert Mercator coordinate list to SVG mm."""
    return [
        (
            round((mx - transformer.x_min) * transformer.scale + transformer.offset_x, 4),
            round((transformer.y_max - my) * transformer.scale + transformer.offset_y, 4),
        )
        for mx, my in coords
    ]


def collect_linestrings(geom) -> list[LineString]:
    """Extract all LineStrings from a Shapely geometry."""
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom] if len(geom.coords) >= 2 else []
    if geom.geom_type == "MultiLineString":
        return [g for g in geom.geoms if len(g.coords) >= 2]
    if geom.geom_type == "GeometryCollection":
        result = []
        for g in geom.geoms:
            result.extend(collect_linestrings(g))
        return result
    return []


def collect_polygons(geom) -> list[Polygon]:
    """Extract all Polygons from a Shapely geometry."""
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        result = []
        for g in geom.geoms:
            result.extend(collect_polygons(g))
        return result
    return []


def project_polygon_to_mercator(polys, transformer):
    """Project WGS84 polygons to Mercator and return as a single union geometry."""
    mercator_polys = []
    for poly in polys:
        projected_ext = [transformer.proj.transform(lon, lat) for lon, lat in poly.exterior.coords]
        projected_holes = [
            [transformer.proj.transform(lon, lat) for lon, lat in hole.coords]
            for hole in poly.interiors
        ]
        mercator_polys.append(Polygon(projected_ext, projected_holes))
    return unary_union(mercator_polys)


def hungary_to_svg_mm_polygon(hungary_polys, transformer):
    """Project Hungary's polygons to SVG mm space and return as a single Polygon/MultiPolygon."""
    svg_polys = []
    for poly in hungary_polys:
        projected_coords = [transformer.proj.transform(lon, lat) for lon, lat in poly.exterior.coords]
        ext_mm = mercator_to_svg_mm(projected_coords, transformer)
        holes_mm = []
        for hole in poly.interiors:
            projected_hole = [transformer.proj.transform(lon, lat) for lon, lat in hole.coords]
            holes_mm.append(mercator_to_svg_mm(projected_hole, transformer))
        svg_polys.append(Polygon(ext_mm, holes_mm))
    return unary_union(svg_polys)


# ---------------------------------------------------------------------------
# SVG generation
# ---------------------------------------------------------------------------


def mm_to_px(val: float) -> float:
    return round(val * MM_TO_PX, 4)


def _make_svg() -> svgwrite.Drawing:
    """Create an SVG Drawing with Inkscape namespace support."""
    w_px = round(WIDTH_MM * MM_TO_PX, 2)
    h_px = round(HEIGHT_MM * MM_TO_PX, 2)
    dwg = svgwrite.Drawing(
        size=(f"{WIDTH_MM}mm", f"{HEIGHT_MM}mm"),
        viewBox=f"0 0 {w_px} {h_px}",
        debug=False,
    )
    dwg.attribs["xmlns:inkscape"] = "http://www.inkscape.org/namespaces/inkscape"
    return dwg


def _build_polyline(dwg, pts_mm, stroke="#000000", stroke_width_mm=BORDER_STROKE_MM):
    """Build a polyline element."""
    pts_px = [(mm_to_px(x), mm_to_px(y)) for x, y in pts_mm]
    sw = mm_to_px(stroke_width_mm)
    return dwg.polyline(
        points=pts_px,
        fill="none",
        stroke=stroke,
        stroke_width=sw,
        stroke_linecap="round",
        stroke_linejoin="round",
    )


def _build_filled_polygon_path(dwg, exterior_coords_mm, holes_mm=None, fill="#000000"):
    """Build a filled polygon path element."""
    def ring_to_d(coords, close=True):
        parts = []
        for i, (x, y) in enumerate(coords):
            px, py = mm_to_px(x), mm_to_px(y)
            cmd = "M" if i == 0 else "L"
            parts.append(f"{cmd}{px},{py}")
        if close:
            parts.append("Z")
        return " ".join(parts)

    d = ring_to_d(exterior_coords_mm)
    if holes_mm:
        for hole in holes_mm:
            d += " " + ring_to_d(hole)

    return dwg.path(d=d, fill=fill, stroke="none", fill_rule="evenodd")


def _build_closed_path_stroke(dwg, coords_mm, stroke_width_mm=WATER_STROKE_MM,
                              stroke_color="#000000"):
    """Build a closed path (outline only) element."""
    pts_px = [(mm_to_px(x), mm_to_px(y)) for x, y in coords_mm]
    sw = mm_to_px(stroke_width_mm)
    d_parts = []
    for i, (px, py) in enumerate(pts_px):
        cmd = "M" if i == 0 else "L"
        d_parts.append(f"{cmd}{px},{py}")
    d_parts.append("Z")
    return dwg.path(
        d=" ".join(d_parts),
        fill="none", stroke=stroke_color, stroke_width=sw,
        stroke_linecap="round", stroke_linejoin="round",
    )


def generate_hatch_lines(polygon_mm, spacing_mm=HATCH_SPACING_MM, angle_deg=HATCH_ANGLE_DEG):
    """Generate parallel hatch lines clipped to a polygon in SVG mm space."""
    centroid = polygon_mm.centroid
    rotated = rotate(polygon_mm, -angle_deg, origin=centroid)
    minx, miny, maxx, maxy = rotated.bounds

    lines = []
    y = miny + spacing_mm
    while y < maxy:
        hline = LineString([(minx - 1, y), (maxx + 1, y)])
        clipped = hline.intersection(rotated)
        for seg in collect_linestrings(clipped):
            lines.append(rotate(seg, angle_deg, origin=centroid))
        y += spacing_mm

    return lines


# ---------------------------------------------------------------------------
# Combined SVG writers
# ---------------------------------------------------------------------------


def write_plotter_svg(border_svg_lines, river_lines, lake_polys,
                      trail_polys, transformer, out_path):
    """Write a single multi-layer plotter SVG with AxiDraw-compatible layers.

    Layers use number-prefixed names per AxiDraw convention:
      1-borders  (1.0mm pen)
      2-water    (0.1mm pen)
      3-trail    (0.1mm pen)
    """
    dwg = _make_svg()

    # Layer 1: borders (1.0mm pen)
    border_group = dwg.g(id="borders")
    border_group.attribs["inkscape:label"] = "1-borders"
    border_group.attribs["inkscape:groupmode"] = "layer"
    for pts in border_svg_lines:
        border_group.add(_build_polyline(dwg, pts, stroke_width_mm=BORDER_STROKE_MM))
    dwg.add(border_group)

    # Layer 2: water (0.1mm pen)
    water_group = dwg.g(id="water")
    water_group.attribs["inkscape:label"] = "2-water"
    water_group.attribs["inkscape:groupmode"] = "layer"
    for line in river_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        water_group.add(_build_polyline(dwg, pts_mm, stroke_width_mm=WATER_STROKE_MM))
    for poly in lake_polys:
        ext_mm = mercator_to_svg_mm(poly.exterior.coords, transformer)
        holes_mm = [mercator_to_svg_mm(hole.coords, transformer) for hole in poly.interiors]
        water_group.add(_build_closed_path_stroke(dwg, ext_mm))
        for hole_mm in holes_mm:
            water_group.add(_build_closed_path_stroke(dwg, hole_mm))
        lake_shape_mm = Polygon(ext_mm, holes_mm)
        for hatch_line in generate_hatch_lines(lake_shape_mm):
            water_group.add(_build_polyline(dwg, list(hatch_line.coords),
                                            stroke_width_mm=WATER_STROKE_MM))
    dwg.add(water_group)

    # Layer 3: trail (0.1mm pen)
    trail_group = dwg.g(id="trail")
    trail_group.attribs["inkscape:label"] = "3-trail"
    trail_group.attribs["inkscape:groupmode"] = "layer"
    for poly in trail_polys:
        ext_mm = list(poly.exterior.coords)
        holes_mm = [list(ring.coords) for ring in poly.interiors]
        trail_group.add(_build_closed_path_stroke(dwg, ext_mm,
                                                  stroke_width_mm=TRAIL_STROKE_MM))
        for hole_mm in holes_mm:
            trail_group.add(_build_closed_path_stroke(dwg, hole_mm,
                                                      stroke_width_mm=TRAIL_STROKE_MM))
        trail_shape_mm = Polygon(ext_mm, holes_mm)
        for hatch_line in generate_hatch_lines(trail_shape_mm):
            trail_group.add(_build_polyline(dwg, list(hatch_line.coords),
                                            stroke_width_mm=TRAIL_STROKE_MM))
    dwg.add(trail_group)

    dwg.saveas(str(out_path))
    print(f"  -> {out_path} (3 layers: borders/{BORDER_STROKE_MM}mm, water/{WATER_STROKE_MM}mm, trail/{TRAIL_STROKE_MM}mm)")


def write_laser_svg(engrave_polys, cut_polys, out_path):
    """Write a single color-coded laser SVG with two Inkscape-compatible layers:
    'Engrave' (black fills) and 'Cut' (red hairline strokes for vector cutting)."""
    dwg = _make_svg()

    # Engrave layer: black filled polygons
    engrave_group = dwg.g(id="engrave")
    engrave_group.attribs["inkscape:label"] = "Engrave"
    engrave_group.attribs["inkscape:groupmode"] = "layer"
    for poly in engrave_polys:
        ext = list(poly.exterior.coords)
        holes = [list(ring.coords) for ring in poly.interiors]
        engrave_group.add(_build_filled_polygon_path(dwg, ext, holes, fill=LASER_ENGRAVE_COLOR))
    dwg.add(engrave_group)

    # Cut layer: red hairline outlines of each polygon
    cut_group = dwg.g(id="cut")
    cut_group.attribs["inkscape:label"] = "Cut"
    cut_group.attribs["inkscape:groupmode"] = "layer"
    for poly in cut_polys:
        ext = list(poly.exterior.coords)
        cut_group.add(_build_closed_path_stroke(dwg, ext,
                                                stroke_width_mm=LASER_HAIRLINE_MM,
                                                stroke_color=LASER_CUT_COLOR))
        for ring in poly.interiors:
            cut_group.add(_build_closed_path_stroke(dwg, list(ring.coords),
                                                    stroke_width_mm=LASER_HAIRLINE_MM,
                                                    stroke_color=LASER_CUT_COLOR))
    dwg.add(cut_group)

    dwg.saveas(str(out_path))
    print(f"  -> {out_path} ({len(engrave_polys)} engrave + {len(cut_polys)} cut shape(s))")


# ---------------------------------------------------------------------------
# Border layer — data extraction
# ---------------------------------------------------------------------------


def extract_border_data(geojson, hungary_polys, hungary_union, transformer):
    """Extract border lines, return SVG mm polylines."""
    print("Finding neighboring countries...")
    hb = hungary_union.bounds
    expand = 1.0
    search_box = box(hb[0] - expand, hb[1] - expand, hb[2] + expand, hb[3] + expand)
    neighbors = find_neighbors(geojson, hungary_union, search_box)
    print(f"  Found neighbors: {', '.join(sorted(neighbors.keys()))}")

    clip_box = transformer.drawable_box_projected()

    print("Processing Hungary's border...")
    hungary_mercator = project_and_clip_border(hungary_polys, transformer, clip_box)
    print(f"  Hungary: {len(hungary_mercator)} line segment(s)")

    print("Processing neighbor borders...")
    all_mercator = list(hungary_mercator)
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

    return mercator_lines_to_svg(deduped, transformer)


def build_border_laser_polys(svg_lines):
    """Buffer border SVG mm lines into filled polygons for laser engraving."""
    shapely_lines = [LineString(pts) for pts in svg_lines if len(pts) >= 2]
    half_w = LASER_BORDER_WIDTH_MM / 2
    buffered = unary_union([
        line.buffer(half_w, cap_style="round", join_style="round")
        for line in shapely_lines
    ])
    clip_rect = box(DRAW_X_MIN, DRAW_Y_MIN, DRAW_X_MAX, DRAW_Y_MAX)
    buffered = buffered.intersection(clip_rect)
    return collect_polygons(buffered)


# ---------------------------------------------------------------------------
# Water layer — data extraction
# ---------------------------------------------------------------------------

WATER_SOURCES = {
    "rivers_global": "ne_10m_rivers_lake_centerlines.geojson",
    "rivers_europe": "ne_10m_rivers_europe.geojson",
    "lakes_global": "ne_10m_lakes.geojson",
    "lakes_europe": "ne_10m_lakes_europe.geojson",
}


def extract_water_features(clip_box_projected, transformer, hungary_mercator=None):
    """Download water GeoJSON files and return clipped river lines and lake polys
    in Mercator coordinates.

    If hungary_mercator is provided, orphan rivers (those not connected to
    Hungary's territory or to lakes/rivers that are) are removed.
    """
    print("  Downloading water data...")
    datasets = {}
    for key, filename in WATER_SOURCES.items():
        url = NE_BASE_URL + filename
        datasets[key] = fetch_geojson(url, filename)

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

    # --- Remove orphan rivers not connected to Hungary ---
    if hungary_mercator is not None and river_lines:
        print("  Removing orphan rivers...")
        touch_buf = 500  # meters in Mercator — generous tolerance for Natural Earth precision
        hungary_buf = hungary_mercator.buffer(touch_buf)
        connected_zone = hungary_buf
        if lake_polys:
            touching_lakes = [lp for lp in lake_polys if lp.intersects(hungary_buf)]
            if touching_lakes:
                connected_zone = unary_union([hungary_buf] + touching_lakes)

        connected = set()
        remaining = set(range(len(river_lines)))
        changed = True
        while changed:
            changed = False
            for i in list(remaining):
                if river_lines[i].intersects(connected_zone):
                    connected.add(i)
                    remaining.discard(i)
                    connected_zone = connected_zone.union(river_lines[i].buffer(touch_buf))
                    changed = True

        orphan_count = len(river_lines) - len(connected)
        river_lines = [river_lines[i] for i in sorted(connected)]
        print(f"  Rivers after orphan removal: {len(river_lines)} segment(s) ({orphan_count} orphan(s) removed)")

    return river_lines, lake_polys


def build_water_laser_polys(river_lines, lake_polys, transformer):
    """Build filled polygons for laser engraving of water features."""
    all_shapes = []

    for line in river_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        if len(pts_mm) >= 2:
            svg_line = LineString(pts_mm)
            all_shapes.append(svg_line.buffer(RIVER_BUFFER_MM, cap_style="round", join_style="round"))

    for poly in lake_polys:
        ext_mm = mercator_to_svg_mm(poly.exterior.coords, transformer)
        holes_mm = [mercator_to_svg_mm(hole.coords, transformer) for hole in poly.interiors]
        lake_shape_mm = Polygon(ext_mm, holes_mm)
        outline = LineString(ext_mm)
        all_shapes.append(outline.buffer(RIVER_BUFFER_MM, cap_style="round", join_style="round"))
        for hole_mm in holes_mm:
            hole_line = LineString(hole_mm)
            all_shapes.append(hole_line.buffer(RIVER_BUFFER_MM, cap_style="round", join_style="round"))
        for hatch_line in generate_hatch_lines(lake_shape_mm):
            all_shapes.append(hatch_line.buffer(RIVER_BUFFER_MM, cap_style="round", join_style="round"))

    if not all_shapes:
        return []

    water_union = unary_union(all_shapes)
    clip_rect = box(DRAW_X_MIN, DRAW_Y_MIN, DRAW_X_MAX, DRAW_Y_MAX)
    water_clipped = water_union.intersection(clip_rect)
    return collect_polygons(water_clipped)


# ---------------------------------------------------------------------------
# Trail layer (GPX)
# ---------------------------------------------------------------------------


def parse_gpx(gpx_path):
    """Parse a GPX file and return a list of (lon, lat) tuples."""
    with open(gpx_path, "r") as f:
        gpx = gpxpy.parse(f)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append((pt.longitude, pt.latitude))
    return points


def extract_trail(gpx_path, clip_box_projected, transformer):
    """Parse GPX, project to Mercator, clip, return list of LineStrings."""
    points = parse_gpx(gpx_path)
    if len(points) < 2:
        return []
    projected = [transformer.proj.transform(lon, lat) for lon, lat in points]
    line = LineString(projected)
    clipped = line.intersection(clip_box_projected)
    return collect_linestrings(clipped)


def build_trail_laser_polys(trail_lines, transformer, lake_polys_mercator=None,
                            hungary_inset_mm=None):
    """Build filled polygons for laser cutting of trail.

    Subtracts lakes and clips to Hungary's inset border.
    """
    half_w = TRAIL_CUT_WIDTH_MM / 2
    all_shapes = []
    for line in trail_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        if len(pts_mm) >= 2:
            svg_line = LineString(pts_mm)
            all_shapes.append(svg_line.buffer(half_w, cap_style="round", join_style="round"))

    if not all_shapes:
        return []

    trail_union = unary_union(all_shapes)
    clip_rect = box(DRAW_X_MIN, DRAW_Y_MIN, DRAW_X_MAX, DRAW_Y_MAX)
    trail_clipped = trail_union.intersection(clip_rect)

    if hungary_inset_mm is not None:
        trail_clipped = trail_clipped.intersection(hungary_inset_mm)
        print(f"  Clipped trail to inside of border (inset {LASER_BORDER_WIDTH_MM / 2}mm)")

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


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main():
    print("=== GPX Tracks to Physical Medium ===\n")

    # --- Setup ---
    print("Loading country data...")
    geojson = fetch_countries_geojson()
    print("Extracting Hungary...")
    hungary_polys = find_country(geojson, "Hungary")
    hungary_union = unary_union(hungary_polys)
    print(f"  Hungary: {len(hungary_polys)} polygon(s)")
    print("Setting up coordinate transform...")
    transformer = CoordTransformer(hungary_union)
    clip_box = transformer.drawable_box_projected()
    hungary_mercator = project_polygon_to_mercator(hungary_polys, transformer)

    # --- Border ---
    print("\n--- Border ---")
    border_svg_lines = extract_border_data(geojson, hungary_polys, hungary_union, transformer)

    # --- Water ---
    print("\n--- Water ---")
    print("Extracting water features...")
    river_lines, lake_polys = extract_water_features(clip_box, transformer, hungary_mercator=hungary_mercator)

    # --- Trail ---
    print("\n--- Trail ---")
    print("Extracting trail from GPX...")
    trail_lines = extract_trail(TRAIL_GPX, clip_box, transformer)
    print(f"  Trail: {len(trail_lines)} segment(s)")

    print("Building Hungary border inset...")
    hungary_mm = hungary_to_svg_mm_polygon(hungary_polys, transformer)
    hungary_inset = hungary_mm.buffer(-LASER_BORDER_WIDTH_MM / 2)

    # --- Build laser polygon sets ---
    print("\n--- Building laser shapes ---")
    border_laser_polys = build_border_laser_polys(border_svg_lines)
    print(f"  Border: {len(border_laser_polys)} polygon(s)")
    water_laser_polys = build_water_laser_polys(river_lines, lake_polys, transformer)
    print(f"  Water: {len(water_laser_polys)} polygon(s)")
    trail_laser_polys = build_trail_laser_polys(trail_lines, transformer,
                                                lake_polys_mercator=lake_polys,
                                                hungary_inset_mm=hungary_inset)
    print(f"  Trail: {len(trail_laser_polys)} polygon(s)")

    # --- Combine border + water for engrave layer ---
    print("\n--- Combining engrave layer (borders + water) ---")
    engrave_union = unary_union(border_laser_polys + water_laser_polys)
    clip_rect = box(DRAW_X_MIN, DRAW_Y_MIN, DRAW_X_MAX, DRAW_Y_MAX)
    engrave_clipped = engrave_union.intersection(clip_rect)
    engrave_polys = collect_polygons(engrave_clipped)
    print(f"  Combined engrave: {len(engrave_polys)} polygon(s)")

    # --- Write output files ---
    print("\n--- Writing output files ---")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_plotter_svg(border_svg_lines, river_lines, lake_polys,
                      trail_laser_polys, transformer, PLOTTER_FILE)
    write_laser_svg(engrave_polys, trail_laser_polys, LASER_FILE)

    # Preview PNG (render plotter SVG at screen resolution)
    png_w = round(WIDTH_MM / 25.4 * PREVIEW_DPI)
    cairosvg.svg2png(url=str(PLOTTER_FILE), write_to=str(PREVIEW_FILE),
                     output_width=png_w, background_color="white")
    print(f"  -> {PREVIEW_FILE} ({png_w}px wide, {PREVIEW_DPI} DPI)")

    # --- Summary ---
    print(f"\n{'='*50}")
    print(f"  Dimensions: {WIDTH_MM}mm x {HEIGHT_MM}mm (A5 landscape)")
    print(f"  Padding: {PADDING_MM}mm")
    print(f"\n  Plotter:")
    print(f"    {PLOTTER_FILE}  — 3 layers (1-borders/{BORDER_STROKE_MM}mm, 2-water/{WATER_STROKE_MM}mm, 3-trail/{TRAIL_STROKE_MM}mm)")
    print(f"\n  Laser:")
    print(f"    {LASER_FILE}  — 2 layers (Engrave=black fill, Cut=red hairline, {TRAIL_CUT_WIDTH_MM}mm slit)")
    print(f"{'='*50}")
    print("\nDone!")


if __name__ == "__main__":
    main()
