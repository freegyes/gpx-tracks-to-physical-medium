"""GeoJSON data fetching and caching."""

import json
from pathlib import Path

import requests

NE_BASE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/"
)
NATURAL_EARTH_URL = NE_BASE_URL + "ne_10m_admin_0_countries.geojson"

WATER_SOURCES = {
    "rivers_global": "ne_10m_rivers_lake_centerlines.geojson",
    "rivers_europe": "ne_10m_rivers_europe.geojson",
    "lakes_global": "ne_10m_lakes.geojson",
    "lakes_europe": "ne_10m_lakes_europe.geojson",
}


def fetch_geojson(url: str, cache_name: str, cache_dir: Path) -> dict:
    """Download a GeoJSON file from a URL, with local caching."""
    cache_path = cache_dir / cache_name
    if cache_path.exists():
        print(f"  Using cached: {cache_path}")
        with open(cache_path, "r") as f:
            return json.load(f)

    print(f"  Downloading {cache_name}...")
    cache_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    with open(cache_path, "w") as f:
        json.dump(data, f)
    print(f"  Cached to {cache_path}")
    return data


def fetch_countries_geojson(cache_dir: Path) -> dict:
    """Download Natural Earth 10m countries GeoJSON, with local caching."""
    return fetch_geojson(NATURAL_EARTH_URL, "ne_10m_admin_0_countries.geojson", cache_dir)
