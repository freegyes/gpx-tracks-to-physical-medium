"""gpx2fab — GPX tracks to fabrication-ready SVGs."""

from .config import GenerationConfig
from .pipeline import GenerationResult, generate

__all__ = ["GenerationConfig", "GenerationResult", "generate"]
