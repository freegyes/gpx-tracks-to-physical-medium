"""Configuration models for GPX-to-fabrication pipeline."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

# Reference design: the original Hungarian OKT project (A5 landscape)
_REF_WIDTH_MM = 210
_REF_HEIGHT_MM = 148
_REF_DIAGONAL = math.hypot(_REF_WIDTH_MM, _REF_HEIGHT_MM)
_REF_CUT_WIDTH_MM = 1.5


class PageConfig(BaseModel):
    width_mm: float = 210
    height_mm: float = 148
    padding_mm: float = 15


class TrailConfig(BaseModel):
    cut_width_mm: float | None = None  # None = auto-scale from reference design
    stroke_mm: float = 0.1


class FabricationConfig(BaseModel):
    border_stroke_mm: float = 1.0
    water_stroke_mm: float = 0.1
    river_buffer_mm: float = 0.15
    hatch_spacing_mm: float = 0.5
    hatch_angle_deg: float = 45
    laser_border_width_mm: float = 1.0
    laser_hairline_mm: float = 0.01
    laser_cut_color: str = "#FF0000"
    laser_engrave_color: str = "#000000"


class StitchConfig(BaseModel):
    enabled: bool = True
    edge: Literal["long", "short", "top", "bottom", "left", "right"] = "long"
    hole_diameter_mm: float = 1.0
    hole_count: int = 5
    offset_mm: float = 10.0
    edge_inset_mm: float = 10.0


class CaptionConfig(BaseModel):
    title: str = ""
    subtitle: str = ""
    title_size_mm: float = 5.0
    subtitle_size_mm: float = 3.5
    title_y_mm: float = 139.0
    subtitle_y_mm: float = 143.5


class GenerationConfig(BaseModel):
    country: str = "Hungary"
    page: PageConfig = PageConfig()
    trail: TrailConfig = TrailConfig()
    fabrication: FabricationConfig = FabricationConfig()
    stitch: StitchConfig = StitchConfig()
    caption: CaptionConfig = CaptionConfig()
    output_plotter: bool = True
    output_laser: bool = True

    @property
    def page_scale(self) -> float:
        """Scale factor of this page relative to the reference 210x148mm design."""
        return math.hypot(self.page.width_mm, self.page.height_mm) / _REF_DIAGONAL

    @property
    def trail_cut_width_mm(self) -> float:
        """Effective trail cut width: explicit value or auto-scaled from reference."""
        if self.trail.cut_width_mm is not None:
            return self.trail.cut_width_mm
        return round(_REF_CUT_WIDTH_MM * self.page_scale, 2)

    @property
    def dpi(self) -> float:
        return 96

    @property
    def mm_to_px_factor(self) -> float:
        return self.dpi / 25.4

    @property
    def draw_x_min(self) -> float:
        return self.page.padding_mm

    @property
    def draw_y_min(self) -> float:
        return self.page.padding_mm

    @property
    def draw_x_max(self) -> float:
        return self.page.width_mm - self.page.padding_mm

    @property
    def draw_y_max(self) -> float:
        return self.page.height_mm - self.page.padding_mm

    @property
    def draw_w(self) -> float:
        return self.draw_x_max - self.draw_x_min

    @property
    def draw_h(self) -> float:
        return self.draw_y_max - self.draw_y_min
