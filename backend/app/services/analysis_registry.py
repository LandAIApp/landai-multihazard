"""Recently completed analyses, so GET /api/v1/analysis/{id} can return them again.

Ephemeral and bounded (per Cloud Run instance, lost on restart or scale-to-zero): no database, no user tracking. Map tile
links inside a stored result are Earth Engine links that expire, so an old result may show its numbers but not its tiles.
"""
from __future__ import annotations

from ..core.cache import TTLCache
from ..core.config import get_settings
from ..schemas.common import HazardResult

_store: dict[str, TTLCache] = {}


def _cache() -> TTLCache:
    return _store.setdefault('results', TTLCache(max_items=max(1, get_settings().analysis_result_items)))


def put(result: HazardResult) -> None:
    _cache().set(result.analysis_id, result, get_settings().analysis_result_ttl_seconds)


def get(analysis_id: str) -> HazardResult | None:
    return _cache().get(analysis_id)


def clear() -> None:
    _store.clear()
