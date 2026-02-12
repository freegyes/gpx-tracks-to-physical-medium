"""Plotter SVG generation."""

from io import StringIO

from shapely.geometry import Polygon

from .config import GenerationConfig
from .geometry import CoordTransformer, mercator_to_svg_mm
from .svg_common import (
    build_closed_path_stroke,
    build_polyline,
    generate_hatch_lines,
    make_svg,
    text_to_svg_path,
)


def write_plotter_svg(border_svg_lines, river_lines, lake_polys,
                      trail_polys, transformer: CoordTransformer,
                      config: GenerationConfig) -> bytes:
    """Write a multi-layer plotter SVG and return as bytes.

    Layers use number-prefixed names per AxiDraw convention:
      1-borders  (1.0mm pen)
      2-water    (0.1mm pen)
      3-trail    (0.1mm pen)
      4-text     (0.1mm pen)
    """
    fab = config.fabrication
    dwg = make_svg(config)

    # Layer 1: borders
    border_group = dwg.g(id="borders")
    border_group.attribs["inkscape:label"] = "1-borders"
    border_group.attribs["inkscape:groupmode"] = "layer"
    for pts in border_svg_lines:
        border_group.add(build_polyline(dwg, pts, config,
                                        stroke_width_mm=fab.border_stroke_mm))
    dwg.add(border_group)

    # Layer 2: water
    water_group = dwg.g(id="water")
    water_group.attribs["inkscape:label"] = "2-water"
    water_group.attribs["inkscape:groupmode"] = "layer"
    for line in river_lines:
        pts_mm = mercator_to_svg_mm(line.coords, transformer)
        water_group.add(build_polyline(dwg, pts_mm, config,
                                       stroke_width_mm=fab.water_stroke_mm))
    for poly in lake_polys:
        ext_mm = mercator_to_svg_mm(poly.exterior.coords, transformer)
        holes_mm = [mercator_to_svg_mm(hole.coords, transformer) for hole in poly.interiors]
        water_group.add(build_closed_path_stroke(dwg, ext_mm, config))
        for hole_mm in holes_mm:
            water_group.add(build_closed_path_stroke(dwg, hole_mm, config))
        lake_shape_mm = Polygon(ext_mm, holes_mm)
        for hatch_line in generate_hatch_lines(lake_shape_mm,
                                                fab.hatch_spacing_mm,
                                                fab.hatch_angle_deg):
            water_group.add(build_polyline(dwg, list(hatch_line.coords), config,
                                           stroke_width_mm=fab.water_stroke_mm))
    dwg.add(water_group)

    # Layer 3: trail
    trail_group = dwg.g(id="trail")
    trail_group.attribs["inkscape:label"] = "3-trail"
    trail_group.attribs["inkscape:groupmode"] = "layer"
    for poly in trail_polys:
        ext_mm = list(poly.exterior.coords)
        holes_mm = [list(ring.coords) for ring in poly.interiors]
        trail_group.add(build_closed_path_stroke(dwg, ext_mm, config,
                                                  stroke_width_mm=config.trail.stroke_mm))
        for hole_mm in holes_mm:
            trail_group.add(build_closed_path_stroke(dwg, hole_mm, config,
                                                      stroke_width_mm=config.trail.stroke_mm))
        trail_shape_mm = Polygon(ext_mm, holes_mm)
        for hatch_line in generate_hatch_lines(trail_shape_mm,
                                                fab.hatch_spacing_mm,
                                                fab.hatch_angle_deg):
            trail_group.add(build_polyline(dwg, list(hatch_line.coords), config,
                                           stroke_width_mm=config.trail.stroke_mm))
    dwg.add(trail_group)

    # Layer 4: text
    caption = config.caption
    if caption.title or caption.subtitle:
        text_group = dwg.g(id="text")
        text_group.attribs["inkscape:label"] = "4-text"
        text_group.attribs["inkscape:groupmode"] = "layer"
        if caption.title:
            text_group.add(text_to_svg_path(
                dwg, caption.title, config.draw_x_max, caption.title_y_mm,
                caption.title_size_mm, config, fill="none", stroke="#000000",
                stroke_width_mm=config.trail.stroke_mm))
        if caption.subtitle:
            text_group.add(text_to_svg_path(
                dwg, caption.subtitle, config.draw_x_max, caption.subtitle_y_mm,
                caption.subtitle_size_mm, config, fill="none", stroke="#000000",
                stroke_width_mm=config.trail.stroke_mm))
        dwg.add(text_group)

    buf = StringIO()
    dwg.write(buf)
    return buf.getvalue().encode("utf-8")
