"""Regression test: regenerate Hungarian Blue Trail output and compare against reference.

Ensures refactoring doesn't silently change fabrication output.
Requires cached geodata in .cache/ and the GPX input file.

    pytest tests/test_hungarian_regression.py       # run regression
    pytest -m "not slow"                            # skip regression
"""

from pathlib import Path

import pytest

from gpx2fab.config import CaptionConfig, GenerationConfig
from gpx2fab.pipeline import generate

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
COUNTRIES_CACHE = CACHE_DIR / "ne_10m_admin_0_countries.geojson"

needs_geodata = pytest.mark.skipif(
    not COUNTRIES_CACHE.exists(),
    reason="Cached geodata not found — run generate_cover.py first to populate .cache/",
)


@pytest.fixture(scope="session")
def hungarian_result(hungarian_gpx_bytes, cache_dir):
    """Generate Hungarian output once for the entire test session."""
    config = GenerationConfig(
        country="Hungary",
        caption=CaptionConfig(title="ORSZÁGOS KÉKTÚRA", subtitle="1172 km"),
    )
    return generate(config, hungarian_gpx_bytes, cache_dir)


@needs_geodata
@pytest.mark.slow
class TestHungarianRegression:
    def test_plotter_svg_matches_reference(self, hungarian_result, hungarian_output_dir):
        ref = (hungarian_output_dir / "plotter_210x148mm.svg").read_bytes()
        assert hungarian_result.plotter_svg == ref, (
            "Plotter SVG differs from reference. If intentional, regenerate:\n"
            "  python3 hungarian-blue-trail/generate_cover.py"
        )

    def test_laser_svg_matches_reference(self, hungarian_result, hungarian_output_dir):
        ref = (hungarian_output_dir / "laser_210x148mm.svg").read_bytes()
        assert hungarian_result.laser_svg == ref, (
            "Laser SVG differs from reference. If intentional, regenerate:\n"
            "  python3 hungarian-blue-trail/generate_cover.py"
        )

    def test_preview_is_valid_png(self, hungarian_result):
        assert hungarian_result.preview_png[:8] == b'\x89PNG\r\n\x1a\n'
