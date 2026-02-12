"""Tests for config auto-scaling and stitch edge resolution."""

import math

import pytest

from gpx2fab.config import (
    GenerationConfig,
    PageConfig,
    StitchConfig,
    TrailConfig,
)
from gpx2fab.svg_laser import _resolve_stitch_edge


class TestTrailCutWidthScaling:
    """Trail cut width should scale proportionally with page diagonal."""

    def test_reference_size_gives_1_5mm(self):
        """210x148mm (reference) should produce exactly 1.5mm."""
        cfg = GenerationConfig()
        assert cfg.trail_cut_width_mm == 1.5

    def test_smaller_page_scales_down(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=150, height_mm=100))
        expected = 1.5 * math.hypot(150, 100) / math.hypot(210, 148)
        assert cfg.trail_cut_width_mm == round(expected, 2)

    def test_larger_page_scales_up(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=210, height_mm=297))
        assert cfg.trail_cut_width_mm > 1.5

    def test_explicit_override_bypasses_scaling(self):
        cfg = GenerationConfig(
            page=PageConfig(width_mm=50, height_mm=50),
            trail=TrailConfig(cut_width_mm=3.0),
        )
        assert cfg.trail_cut_width_mm == 3.0

    def test_half_size_page_gives_half_scale(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=105, height_mm=74))
        assert cfg.page_scale == pytest.approx(0.5, abs=0.01)


class TestStitchEdgeResolution:
    """Stitch holes should auto-orient to the correct edge."""

    def test_long_edge_landscape(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=210, height_mm=148))
        assert _resolve_stitch_edge(cfg) == "top"

    def test_long_edge_portrait(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=210, height_mm=297))
        assert _resolve_stitch_edge(cfg) == "left"

    def test_short_edge_is_opposite_of_long(self):
        cfg = GenerationConfig(
            page=PageConfig(width_mm=210, height_mm=148),
            stitch=StitchConfig(edge="short"),
        )
        assert _resolve_stitch_edge(cfg) == "left"

    def test_explicit_edges_pass_through(self):
        for edge in ("top", "bottom", "left", "right"):
            cfg = GenerationConfig(stitch=StitchConfig(edge=edge))
            assert _resolve_stitch_edge(cfg) == edge

    def test_square_page_resolves_to_top(self):
        cfg = GenerationConfig(page=PageConfig(width_mm=100, height_mm=100))
        assert _resolve_stitch_edge(cfg) == "top"
