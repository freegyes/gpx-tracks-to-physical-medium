"""Laser SVG generation."""

from io import StringIO

from .config import GenerationConfig
from .svg_common import (
    build_closed_path_stroke,
    build_filled_polygon_path,
    make_svg,
    mm_to_px,
    text_to_svg_path,
)


def _resolve_stitch_edge(config: GenerationConfig) -> str:
    """Resolve 'long'/'short' to a concrete edge based on page dimensions."""
    edge = config.stitch.edge
    if edge in ("top", "bottom", "left", "right"):
        return edge
    w, h = config.page.width_mm, config.page.height_mm
    if edge == "long":
        return "top" if w >= h else "left"
    else:  # "short"
        return "top" if w < h else "left"


def _add_stitch_holes(dwg, group, config: GenerationConfig):
    """Add stitching holes as circles on the cut layer."""
    stitch = config.stitch
    fab = config.fabrication
    w, h = config.page.width_mm, config.page.height_mm
    edge = _resolve_stitch_edge(config)

    r = mm_to_px(stitch.hole_diameter_mm / 2, config)

    if edge in ("top", "bottom"):
        # Holes spread horizontally
        span_start = stitch.edge_inset_mm
        span_end = w - stitch.edge_inset_mm
        fixed = stitch.offset_mm if edge == "top" else h - stitch.offset_mm
        spacing = (span_end - span_start) / (stitch.hole_count - 1)
        for i in range(stitch.hole_count):
            cx = mm_to_px(span_start + i * spacing, config)
            cy = mm_to_px(fixed, config)
            group.add(dwg.circle(
                center=(cx, cy), r=r,
                fill="none", stroke=fab.laser_cut_color,
                stroke_width=mm_to_px(fab.laser_hairline_mm, config),
            ))
    else:
        # Holes spread vertically
        span_start = stitch.edge_inset_mm
        span_end = h - stitch.edge_inset_mm
        fixed = stitch.offset_mm if edge == "left" else w - stitch.offset_mm
        spacing = (span_end - span_start) / (stitch.hole_count - 1)
        for i in range(stitch.hole_count):
            cx = mm_to_px(fixed, config)
            cy = mm_to_px(span_start + i * spacing, config)
            group.add(dwg.circle(
                center=(cx, cy), r=r,
                fill="none", stroke=fab.laser_cut_color,
                stroke_width=mm_to_px(fab.laser_hairline_mm, config),
            ))


def _add_contour_cut(dwg, group, config: GenerationConfig):
    """Add a contour-cut rectangle to a cut group."""
    w = config.page.width_mm
    h = config.page.height_mm
    contour = [(0, 0), (w, 0), (w, h), (0, h)]
    group.add(build_closed_path_stroke(dwg, contour, config,
                                        stroke_width_mm=config.fabrication.laser_hairline_mm,
                                        stroke_color=config.fabrication.laser_cut_color))


def write_laser_svg(engrave_polys, trail_polys, config: GenerationConfig) -> bytes:
    """Write a laser SVG with 4 Inkscape-compatible layers, return as bytes.

      1-Trail   — red hairline cut
      2-Contour — red hairline cut
      3-Stitch  — red hairline cut
      4-Engrave — black fill
    """
    fab = config.fabrication
    caption = config.caption
    dwg = make_svg(config)

    # Layer 1: Trail cut
    trail_group = dwg.g(id="trail")
    trail_group.attribs["inkscape:label"] = "1-Trail"
    trail_group.attribs["inkscape:groupmode"] = "layer"
    for poly in trail_polys:
        ext = list(poly.exterior.coords)
        trail_group.add(build_closed_path_stroke(dwg, ext, config,
                                                  stroke_width_mm=fab.laser_hairline_mm,
                                                  stroke_color=fab.laser_cut_color))
        for ring in poly.interiors:
            trail_group.add(build_closed_path_stroke(dwg, list(ring.coords), config,
                                                      stroke_width_mm=fab.laser_hairline_mm,
                                                      stroke_color=fab.laser_cut_color))
    dwg.add(trail_group)

    # Layer 2: Contour cut
    contour_group = dwg.g(id="contour")
    contour_group.attribs["inkscape:label"] = "2-Contour"
    contour_group.attribs["inkscape:groupmode"] = "layer"
    _add_contour_cut(dwg, contour_group, config)
    dwg.add(contour_group)

    # Layer 3: Stitch holes
    if config.stitch.enabled:
        stitch_group = dwg.g(id="stitch")
        stitch_group.attribs["inkscape:label"] = "3-Stitch"
        stitch_group.attribs["inkscape:groupmode"] = "layer"
        _add_stitch_holes(dwg, stitch_group, config)
        dwg.add(stitch_group)

    # Layer 4: Engrave
    engrave_group = dwg.g(id="engrave")
    engrave_group.attribs["inkscape:label"] = "4-Engrave"
    engrave_group.attribs["inkscape:groupmode"] = "layer"
    for poly in engrave_polys:
        ext = list(poly.exterior.coords)
        holes = [list(ring.coords) for ring in poly.interiors]
        engrave_group.add(build_filled_polygon_path(dwg, ext, config,
                                                     holes, fill=fab.laser_engrave_color))
    if caption.title:
        engrave_group.add(text_to_svg_path(
            dwg, caption.title, config.draw_x_max, caption.title_y_mm,
            caption.title_size_mm, config, fill=fab.laser_engrave_color))
    if caption.subtitle:
        engrave_group.add(text_to_svg_path(
            dwg, caption.subtitle, config.draw_x_max, caption.subtitle_y_mm,
            caption.subtitle_size_mm, config, fill=fab.laser_engrave_color))
    dwg.add(engrave_group)

    buf = StringIO()
    dwg.write(buf)
    return buf.getvalue().encode("utf-8")
