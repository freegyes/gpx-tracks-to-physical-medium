"""Coordinate transformation and geometry helpers."""

from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box
from shapely.ops import linemerge, unary_union

from .config import GenerationConfig


class CoordTransformer:
    """WGS84 -> Web Mercator -> SVG mm coordinates, fitted to a country's bounds."""

    def __init__(self, country_union, config: GenerationConfig):
        self.proj = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        self._config = config

        # Project country's bounding box
        minx, miny, maxx, maxy = country_union.bounds  # lon/lat
        x_min, y_min = self.proj.transform(minx, miny)
        x_max, y_max = self.proj.transform(maxx, maxy)

        draw_w = config.draw_w
        draw_h = config.draw_h

        # Uniform scale (fit-contain), reduced slightly so neighbor borders
        # have room to extend beyond the country on the tight-fitting axis
        INSET = 0.92
        sx = draw_w / (x_max - x_min)
        sy = draw_h / (y_max - y_min)
        self.scale = min(sx, sy) * INSET

        # Center offset
        projected_w = (x_max - x_min) * self.scale
        projected_h = (y_max - y_min) * self.scale
        self.offset_x = config.draw_x_min + (draw_w - projected_w) / 2
        self.offset_y = config.draw_y_min + (draw_h - projected_h) / 2

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
        cfg = self._config
        x_min_m = (cfg.draw_x_min - self.offset_x) / self.scale + self.x_min
        x_max_m = (cfg.draw_x_max - self.offset_x) / self.scale + self.x_min
        y_max_m = self.y_max - (cfg.draw_y_min - self.offset_y) / self.scale
        y_min_m = self.y_max - (cfg.draw_y_max - self.offset_y) / self.scale
        return box(x_min_m, y_min_m, x_max_m, y_max_m)


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


def find_neighbors(geojson: dict, country_union, search_box,
                   country_name: str) -> dict[str, list[Polygon]]:
    """Find all countries whose geometry intersects the expanded search box,
    excluding the target country itself."""
    neighbors = {}
    for feat in geojson["features"]:
        props = feat.get("properties", {})
        name = props.get("NAME", "")
        if name == country_name:
            continue
        polys = feature_to_polygons(feat)
        if not polys:
            continue
        feat_union = unary_union(polys)
        if feat_union.intersects(search_box):
            neighbors[name] = polys
    return neighbors


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


def mercator_to_svg_mm(coords, transformer: CoordTransformer):
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


def remove_orphan_geometries(geometries, seed_zone, tolerance=500):
    """Remove geometries not connected to a seed zone via flood-fill.

    Starting from seed_zone, iteratively expands by buffering each connected
    geometry. Geometries that never intersect the expanding zone are orphans.

    Args:
        geometries: list of Shapely geometries to filter.
        seed_zone: initial Shapely geometry to flood-fill from.
        tolerance: buffer distance (in geometry's CRS units) for connectivity.

    Returns:
        list of connected geometries, in original order.
    """
    if not geometries:
        return geometries

    zone = seed_zone
    connected = set()
    remaining = set(range(len(geometries)))
    changed = True
    while changed:
        changed = False
        for i in list(remaining):
            if geometries[i].intersects(zone):
                connected.add(i)
                remaining.discard(i)
                zone = zone.union(geometries[i].buffer(tolerance))
                changed = True

    return [geometries[i] for i in sorted(connected)]


def project_polygon_to_mercator(polys, transformer: CoordTransformer):
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


def country_to_svg_mm_polygon(country_polys, transformer: CoordTransformer):
    """Project a country's polygons to SVG mm space and return as a single Polygon/MultiPolygon."""
    svg_polys = []
    for poly in country_polys:
        projected_coords = [transformer.proj.transform(lon, lat) for lon, lat in poly.exterior.coords]
        ext_mm = mercator_to_svg_mm(projected_coords, transformer)
        holes_mm = []
        for hole in poly.interiors:
            projected_hole = [transformer.proj.transform(lon, lat) for lon, lat in hole.coords]
            holes_mm.append(mercator_to_svg_mm(projected_hole, transformer))
        svg_polys.append(Polygon(ext_mm, holes_mm))
    return unary_union(svg_polys)
