"""Hazard registry: ``get_engine('wildfire' | 'flood')``."""
from __future__ import annotations

from ..core.errors import HazardNotFoundError
from .base import HazardEngine

_engines: dict[str, HazardEngine] = {}
HAZARD_IDS = ('wildfire', 'flood')


def _build(hazard: str) -> HazardEngine:
    if hazard == 'wildfire':
        from .wildfire.engine import WildfireEngine
        return WildfireEngine()
    if hazard == 'flood':
        from .flood.engine import FloodEngine
        return FloodEngine()
    raise HazardNotFoundError(f"Unknown hazard '{hazard}'. Available: {', '.join(HAZARD_IDS)}.")


def get_engine(hazard: str) -> HazardEngine:
    if hazard not in _engines:
        _engines[hazard] = _build(hazard)
    return _engines[hazard]


def all_engines() -> list[HazardEngine]:
    return [get_engine(h) for h in HAZARD_IDS]
