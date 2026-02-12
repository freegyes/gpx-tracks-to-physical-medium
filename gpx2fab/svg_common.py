"""Shared SVG building utilities."""

import cairocffi as cairo
import svgwrite
from shapely.affinity import rotate
from shapely.geometry import LineString

from .config import GenerationConfig
from .geometry import collect_linestrings


def mm_to_px(val: float, config: GenerationConfig) -> float:
    return round(val * config.mm_to_px_factor, 4)


def make_svg(config: GenerationConfig) -> svgwrite.Drawing:
    """Create an SVG Drawing with Inkscape namespace support."""
    factor = config.mm_to_px_factor
    w_mm = config.page.width_mm
    h_mm = config.page.height_mm
    w_px = round(w_mm * factor, 2)
    h_px = round(h_mm * factor, 2)
    dwg = svgwrite.Drawing(
        size=(f"{w_mm}mm", f"{h_mm}mm"),
        viewBox=f"0 0 {w_px} {h_px}",
        debug=False,
    )
    dwg.attribs["xmlns:inkscape"] = "http://www.inkscape.org/namespaces/inkscape"
    return dwg


def build_polyline(dwg, pts_mm, config: GenerationConfig,
                   stroke="#000000", stroke_width_mm=None):
    """Build a polyline element."""
    if stroke_width_mm is None:
        stroke_width_mm = config.fabrication.border_stroke_mm
    pts_px = [(mm_to_px(x, config), mm_to_px(y, config)) for x, y in pts_mm]
    sw = mm_to_px(stroke_width_mm, config)
    return dwg.polyline(
        points=pts_px,
        fill="none",
        stroke=stroke,
        stroke_width=sw,
        stroke_linecap="round",
        stroke_linejoin="round",
    )


def build_filled_polygon_path(dwg, exterior_coords_mm, config: GenerationConfig,
                              holes_mm=None, fill="#000000"):
    """Build a filled polygon path element."""
    def ring_to_d(coords, close=True):
        parts = []
        for i, (x, y) in enumerate(coords):
            px, py = mm_to_px(x, config), mm_to_px(y, config)
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


def build_closed_path_stroke(dwg, coords_mm, config: GenerationConfig,
                             stroke_width_mm=None, stroke_color="#000000"):
    """Build a closed path (outline only) element."""
    if stroke_width_mm is None:
        stroke_width_mm = config.fabrication.water_stroke_mm
    pts_px = [(mm_to_px(x, config), mm_to_px(y, config)) for x, y in coords_mm]
    sw = mm_to_px(stroke_width_mm, config)
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


def text_to_svg_path(dwg, text, x_mm, y_mm, font_size_mm, config: GenerationConfig,
                     fill="none", stroke="#000000", stroke_width_mm=0):
    """Render text to outlined SVG <path> elements using cairocffi.

    The text is right-aligned: x_mm is the right edge, y_mm is the baseline.
    """
    CAIRO_FONT_SIZE = 100

    surface = cairo.RecordingSurface(cairo.CONTENT_ALPHA, None)
    ctx = cairo.Context(surface)
    ctx.select_font_face("Helvetica Neue", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(CAIRO_FONT_SIZE)

    ctx.move_to(0, 0)
    ctx.text_path(text)
    total_advance = ctx.get_scaled_font().text_extents(text)[4]

    scale = font_size_mm / CAIRO_FONT_SIZE
    ox = x_mm - total_advance * scale
    oy = y_mm

    d_parts = []
    for op_type, points in ctx.copy_path():
        if op_type == 0:  # MOVE_TO
            px = mm_to_px(points[0] * scale + ox, config)
            py = mm_to_px(points[1] * scale + oy, config)
            d_parts.append(f"M{px},{py}")
        elif op_type == 1:  # LINE_TO
            px = mm_to_px(points[0] * scale + ox, config)
            py = mm_to_px(points[1] * scale + oy, config)
            d_parts.append(f"L{px},{py}")
        elif op_type == 2:  # CURVE_TO
            coords = []
            for i in range(0, 6, 2):
                coords.append(mm_to_px(points[i] * scale + ox, config))
                coords.append(mm_to_px(points[i + 1] * scale + oy, config))
            d_parts.append(f"C{coords[0]},{coords[1]} {coords[2]},{coords[3]} {coords[4]},{coords[5]}")
        elif op_type == 3:  # CLOSE_PATH
            d_parts.append("Z")

    d = " ".join(d_parts)

    attrs = {"fill": fill}
    if stroke_width_mm > 0:
        attrs["stroke"] = stroke
        attrs["stroke_width"] = mm_to_px(stroke_width_mm, config)
    else:
        attrs["stroke"] = "none"

    return dwg.path(d=d, **attrs)


def generate_hatch_lines(polygon_mm, spacing_mm=0.5, angle_deg=45):
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
