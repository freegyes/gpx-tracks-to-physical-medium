# Hungarian Blue Trail

A5 landscape (210x148mm) notebook cover showing Hungary's border, water features, and the OKT (Orszagos Kektura) hiking trail. The trail is rendered as a see-through slit in the laser version, so the colour of the page underneath shows through.

![Preview](output/preview.png)

## Setup

```bash
pip install -r requirements.txt
```

Dependencies: svgwrite, shapely, pyproj, gpxpy, cairocffi, cairosvg, requests.

## Generate

```bash
python3 hungarian-blue-trail/generate_cover.py
```

Geographic data (Natural Earth 10m vectors) is downloaded on first run and cached in `.cache/` at the repo root. The GPX track lives in `input/`.

## Output

Two fabrication-ready SVGs are written to `output/`, plus a raster preview:

```
output/
  plotter_210x148mm.svg  # pen plotter
  laser_210x148mm.svg    # laser cutter
  preview.png            # raster preview (plotter SVG rendered at 150 DPI)
```

### Plotter SVG

Single multi-layer SVG with AxiDraw-compatible layer names (number-prefixed so they sort correctly):

| Layer | Content | Pen width |
|-------|---------|-----------|
| `1-borders` | Country borders (Hungary + neighbors, clipped to page) | 1.0 mm |
| `2-water` | Rivers + hatched lakes | 0.1 mm |
| `3-trail` | OKT trail, hatched to 1.5 mm width | 0.1 mm |
| `4-text` | Caption ("ORSZAGOS KEKTURA" + "1172 km"), outlined paths | 0.1 mm |

### Laser SVG

Single multi-layer SVG, color-coded for a typical laser workflow (red = vector cut, black = raster engrave):

| Layer | Type | Content |
|-------|------|---------|
| `1-Trail` | Cut (red hairline) | See-through GPX track slit, 1.5 mm wide |
| `2-Contour` | Cut (red hairline) | Outer 210x148 mm rectangle |
| `3-Stitch` | Cut (red hairline) | 5 x 1 mm holes along the spine for bookbinding |
| `4-Engrave` | Engrave (black fill) | Borders + water + caption text |

## How it works

1. Hungary's border and neighbors are extracted from Natural Earth 10m country polygons
2. Rivers and lakes are pulled from Natural Earth water datasets; orphan rivers not connected to Hungary are filtered out
3. The OKT trail is parsed from a GPX file
4. Everything is projected (WGS84 -> Web Mercator) and fitted to the A5 page using a shared `CoordTransformer`
5. For the laser version, the trail slit is clipped to the inner edge of the border and lakes are subtracted so it doesn't cut through water features
6. Text is converted to outlined `<path>` elements via cairocffi (no font dependencies at fabrication time)

All layers share the same coordinate transform, so they align when overlaid.
