"""WorldPop population estimate for the real affected footprint (WorldPop API V3, synchronous).

Contract (WorldPop public API V3):

    POST {base}/v3/population      body: {"geojson": <Feature|Polygon|MultiPolygon>, "year": 2020}

The answer is synchronous: ``total_population`` (plus ``area_km2``, ``population_density``, ``data_year``,
``data_source``, ``processing_time_ms``). There is NO task polling any more.

Why the geometry is prepared before it is sent
----------------------------------------------
A wildfire / flood footprint is a raster outline with very many parts and vertices; a single request with all of
it can be refused with HTTP 413. The footprint is therefore:

1. validated (``make_valid``) and DISSOLVED (``unary_union``) so overlapping parts are never counted twice;
2. cleaned of empty geometries and of slivers smaller than ``WORLDPOP_MIN_PART_AREA_M2`` (default 50 m², half a
   10 m Sentinel pixel: far below the 100 m resolution of the population grid);
3. simplified (topology preserving) ONLY when it still has more than ``WORLDPOP_MAX_VERTICES`` vertices; the vertex
   and area change are reported;
4. split into bounded groups of DISJOINT polygon parts (``WORLDPOP_CHUNK_VERTICES`` / ``WORLDPOP_CHUNK_PARTS``) that
   are sent one after another. Populations of disjoint groups are summed, so nothing is counted twice.

HTTP 413 never means "unavailable" by itself: the group is halved and retried (down to a single part, which is then
simplified harder once). A group that still fails marks the result PARTIAL only when the successful groups cover at
least ``WORLDPOP_MIN_PARTIAL_COVERAGE_PCT`` of the footprint area (the value is then a lower bound and says so);
otherwise the source is UNAVAILABLE. A failure is never turned into zero.

Population year is a configuration value (WORLDPOP_YEAR); it is NOT derived from the event date.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import httpx
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from ..core.cache import TTLCache
from ..core.config import Settings
from ..core.errors import ExternalSourceError
from . import spatial

logger = logging.getLogger('landai.worldpop')
_cache = TTLCache(max_items=64)           # whole, fully successful estimates
_chunk_cache = TTLCache(max_items=512)    # successful groups: a retry after a partial result re-asks only the failed ones

POPULATION_KEYS = ('total_population', 'population', 'total', 'sum', 'estimate')
DATASET_LABEL = 'WorldPop gridded population (100 m)'


@dataclass
class PopulationResult:
    estimate: float
    year: int
    resolution: str
    dataset: str
    api_version: str
    task_id: str | None                 # always None with V3 (no tasks); kept for response compatibility
    analysis_area_ha: float
    simplification: dict = field(default_factory=dict)
    retrieved_at: str = ''
    from_cache: bool = False
    partial: bool = False               # True: lower bound, some groups of parts failed
    chunks: int = 1
    chunks_failed: int = 0
    parts: int = 1
    coverage_pct: float = 100.0         # share of the footprint area that the answered groups cover
    failures: list = field(default_factory=list)
    data_year: int | None = None
    data_source: str | None = None
    processing_time_ms: float | None = None
    request_count: int = 1


def clear_cache() -> None:
    _cache.clear()
    _chunk_cache.clear()


# ------------------------------------------------------------------------------------------------
# Geometry preparation
# ------------------------------------------------------------------------------------------------
@dataclass
class Prepared:
    parts_metric: list[Polygon]          # dissolved, disjoint, cleaned (metric CRS)
    report: dict


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, 'geoms'):
        out: list[Polygon] = []
        for g in geom.geoms:
            out.extend(_polygons(g))
        return out
    return []                              # points / lines produced by make_valid are not areas


def prepare(hazard_metric: BaseGeometry, settings: Settings) -> Prepared:
    """Validate, dissolve, clean and (only if needed) simplify. Every step is measured and reported."""
    raw_vertices = spatial.count_vertices(hazard_metric)
    raw_parts = len(_polygons(hazard_metric))
    area_before = hazard_metric.area
    geom = hazard_metric if hazard_metric.is_valid else make_valid(hazard_metric)
    dissolved = unary_union(_polygons(geom))            # overlapping polygons are merged: no double counting
    parts = [p for p in _polygons(dissolved) if not p.is_empty]
    slivers = [p for p in parts if p.area < settings.worldpop_min_part_area_m2]
    if slivers and len(slivers) < len(parts):
        parts = [p for p in parts if p.area >= settings.worldpop_min_part_area_m2]
    else:
        slivers = []
    removed_area = sum(p.area for p in slivers)
    vertices_dissolved = sum(spatial.count_vertices(p) for p in parts)
    report = {'applied': False, 'tolerance_m': 0.0, 'vertices_raw': raw_vertices, 'parts_raw': raw_parts,
              'vertices_before': vertices_dissolved, 'vertices_after': vertices_dissolved, 'parts': len(parts),
              'dissolved': True, 'parts_dropped': len(slivers), 'dropped_area_m2': round(removed_area, 2),
              'area_change_pct': 0.0}
    if vertices_dissolved > settings.worldpop_max_vertices and parts:
        tolerance = settings.worldpop_simplify_tolerance_m
        simplified = parts
        for _ in range(6):
            simplified = [q for q in (p.simplify(tolerance, preserve_topology=True) for p in parts) if not q.is_empty]
            if sum(spatial.count_vertices(p) for p in simplified) <= settings.worldpop_max_vertices:
                break
            tolerance *= 2
        merged = unary_union(simplified)               # simplification can make neighbours touch/overlap
        parts = [p for p in _polygons(merged) if not p.is_empty]
        after = sum(spatial.count_vertices(p) for p in parts)
        report.update(applied=True, tolerance_m=tolerance, vertices_after=after, parts=len(parts))
    total = sum(p.area for p in parts)
    base = area_before if area_before else total
    report['area_change_pct'] = round((total - base) / base * 100.0, 3) if base else 0.0
    report['area_m2'] = round(total, 2)
    return Prepared(parts_metric=parts, report=report)


def prepare_geometry(hazard_metric: BaseGeometry, crs: str, settings: Settings) -> tuple[BaseGeometry, dict]:
    """(WGS84 MultiPolygon/Polygon of the prepared parts, report). Kept for callers that need one geometry."""
    prepared = prepare(hazard_metric, settings)
    parts = prepared.parts_metric
    geom = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    return spatial.to_wgs84(geom, crs), prepared.report


def _group(parts: list[Polygon], settings: Settings) -> list[list[Polygon]]:
    """Bounded groups of disjoint parts, spatially ordered so every group is compact."""
    if not parts:
        return []
    ordered = sorted(parts, key=lambda p: (round(p.centroid.y / 3000.0), p.centroid.x))
    groups: list[list[Polygon]] = []
    current: list[Polygon] = []
    vertices = 0
    for part in ordered:
        n = spatial.count_vertices(part)
        if current and (vertices + n > settings.worldpop_chunk_vertices
                        or len(current) >= settings.worldpop_chunk_parts):
            groups.append(current)
            current, vertices = [], 0
        current.append(part)
        vertices += n
    if current:
        groups.append(current)
    return groups


def _feature(parts_metric: list[Polygon], crs: str) -> dict:
    geom = parts_metric[0] if len(parts_metric) == 1 else MultiPolygon(parts_metric)
    wgs = spatial.round_coords(spatial.to_wgs84(geom, crs), 6)
    return {'type': 'Feature', 'properties': {}, 'geometry': mapping(wgs)}


# ------------------------------------------------------------------------------------------------
# Response handling
# ------------------------------------------------------------------------------------------------
def _fail(message: str, code: str, status_code: int = 502, **details) -> ExternalSourceError:
    return ExternalSourceError(message, code=code, status_code=status_code, details=details or None)


def _extract_total(payload) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in POPULATION_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    for key in ('data', 'result', 'results'):
        found = _extract_total(payload.get(key))
        if found is not None:
            return found
    return None


def _json(response: httpx.Response) -> dict:
    status = response.status_code
    if status == 413:
        raise _fail('WorldPop refused the request because it is too large.', 'worldpop_payload_too_large', 413,
                    http_status=413)
    if status == 429:
        raise _fail('WorldPop rate limit reached. Try again later.', 'worldpop_rate_limited', 429, http_status=429,
                    retry_after=response.headers.get('retry-after'))
    if status >= 400:
        raise _fail(f'WorldPop answered HTTP {status}.', 'worldpop_http_error',
                    502 if status >= 500 else 422, http_status=status)
    try:
        payload = response.json()
    except ValueError as exc:
        raise _fail('WorldPop returned a response that is not JSON.', 'worldpop_bad_response') from exc
    if not isinstance(payload, dict):
        raise _fail('WorldPop returned an unexpected response.', 'worldpop_bad_response')
    return payload


def _wait_seconds(exc: ExternalSourceError, settings: Settings) -> float:
    retry_after = exc.details.get('retry_after') if isinstance(exc.details, dict) else None
    try:
        wait = float(retry_after)
    except (TypeError, ValueError):
        wait = settings.worldpop_retry_wait_s
    return max(0.5, min(wait, settings.worldpop_retry_wait_s * 3))


# ------------------------------------------------------------------------------------------------
# Requests
# ------------------------------------------------------------------------------------------------
@dataclass
class _Ctx:
    client: httpx.Client
    base: str
    settings: Settings
    sleep: Callable[[float], None]
    crs: str
    requests: int = 0
    aborted: ExternalSourceError | None = None     # 429 / 5xx after a retry: the service is not coping, stop asking


def _chunk_key(settings: Settings, body: dict) -> tuple:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return (settings.worldpop_base_url, settings.worldpop_api_version, settings.worldpop_year, digest)


def _post_once(ctx: _Ctx, feature: dict) -> dict:
    body = {'geojson': feature, 'year': ctx.settings.worldpop_year}
    key = _chunk_key(ctx.settings, body)
    cached = _chunk_cache.get(key)
    if cached is not None:
        return {**cached, '_cached': True}
    ctx.requests += 1
    try:
        response = ctx.client.post(f'{ctx.base}/v3/population', json=body)
    except httpx.TimeoutException as exc:
        raise _fail('WorldPop did not answer in time.', 'worldpop_timeout', 504) from exc
    except httpx.HTTPError as exc:
        raise _fail('WorldPop could not be reached.', 'worldpop_unreachable') from exc
    payload = _json(response)
    total = _extract_total(payload)
    if total is None or total != total or total < 0:
        raise _fail('WorldPop returned no valid population value.', 'worldpop_bad_response')
    out = {'total': total, 'data_year': payload.get('data_year'), 'data_source': payload.get('data_source'),
           'processing_time_ms': payload.get('processing_time_ms'), 'area_km2': payload.get('area_km2')}
    _chunk_cache.set(key, out, ctx.settings.worldpop_cache_ttl_seconds)
    return out


def _post_with_retry(ctx: _Ctx, feature: dict) -> dict:
    """One request; a 429/5xx/timeout is retried ONCE after the (bounded) wait the service asks for."""
    try:
        return _post_once(ctx, feature)
    except ExternalSourceError as exc:
        if exc.code not in ('worldpop_rate_limited', 'worldpop_timeout') and not (
                exc.code == 'worldpop_http_error' and (exc.details or {}).get('http_status', 0) >= 500):
            raise
        logger.warning('worldpop_retry code=%s', exc.code)
        ctx.sleep(_wait_seconds(exc, ctx.settings))
    return _post_once(ctx, feature)


def _solve(ctx: _Ctx, parts: list[Polygon], depth: int = 0) -> tuple[list[dict], list[tuple[list[Polygon], ExternalSourceError]]]:
    """Population of a group of disjoint parts. On HTTP 413 the group is halved; a single part is simplified once
    more. Returns (answers, failed groups); the failed groups are NEVER summed as zero."""
    if ctx.aborted is not None:
        return [], [(parts, ctx.aborted)]
    try:
        return [_post_with_retry(ctx, _feature(parts, ctx.crs)) | {'_area': sum(p.area for p in parts)}], []
    except ExternalSourceError as exc:
        if exc.code == 'worldpop_payload_too_large':
            if len(parts) > 1:
                mid = len(parts) // 2
                a_ok, a_bad = _solve(ctx, parts[:mid], depth + 1)
                b_ok, b_bad = _solve(ctx, parts[mid:], depth + 1)
                return a_ok + b_ok, a_bad + b_bad
            if depth < 12:
                tolerance = max(ctx.settings.worldpop_simplify_tolerance_m, 5.0) * 4
                simpler = parts[0].simplify(tolerance, preserve_topology=True)
                if not simpler.is_empty and spatial.count_vertices(simpler) < spatial.count_vertices(parts[0]):
                    return _solve(ctx, _polygons(simpler), 12)       # one more attempt only
        if exc.code in ('worldpop_rate_limited', 'worldpop_unreachable') or (
                exc.code == 'worldpop_http_error' and (exc.details or {}).get('http_status', 0) >= 500):
            ctx.aborted = exc
        return [], [(parts, exc)]


# ------------------------------------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------------------------------------
def estimate(hazard_metric: BaseGeometry, crs: str, settings: Settings, *,
             transport: httpx.BaseTransport | None = None,
             sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic) -> PopulationResult:
    """Population inside the real footprint polygon. Raises ExternalSourceError when unavailable.

    A result with ``partial=True`` is a lower bound (some disjoint groups of parts could not be answered)."""
    if settings.worldpop_api_version.lower() != 'v3':
        raise _fail(f"WORLDPOP_API_VERSION='{settings.worldpop_api_version}' is no longer supported; use v3.",
                    'worldpop_unsupported_version', 500)
    prepared = prepare(hazard_metric, settings)
    parts = prepared.parts_metric
    if not parts:
        raise _fail('The footprint has no valid area to send to WorldPop.', 'worldpop_geometry_empty', 422)
    groups = _group(parts, settings)
    if len(groups) > settings.worldpop_max_chunks:
        raise _fail('The affected area geometry is too fragmented to send to WorldPop.',
                    'worldpop_geometry_too_complex', 422,
                    chunks=len(groups), max_chunks=settings.worldpop_max_chunks,
                    vertices=prepared.report['vertices_after'])

    digest = hashlib.sha256('|'.join(
        shapely.to_wkt(g, rounding_precision=1, trim=True, output_dimension=2)
        for g in sorted(parts, key=lambda p: (p.bounds, p.area))).encode()).hexdigest()
    cache_key = (settings.worldpop_base_url, settings.worldpop_api_version, settings.worldpop_year,
                 settings.worldpop_resolution, crs, digest)
    cached = _cache.get(cache_key)
    if cached is not None:
        cached.from_cache = True
        return cached

    headers = {'User-Agent': settings.overpass_user_agent, 'Accept': 'application/json'}
    if settings.worldpop_api_key:
        headers['X-API-Key'] = settings.worldpop_api_key           # server-side only, never logged or returned
    started = clock()
    with httpx.Client(headers=headers, timeout=settings.worldpop_http_timeout_s, transport=transport) as client:
        ctx = _Ctx(client=client, base=settings.worldpop_base_url.rstrip('/'), settings=settings, sleep=sleep, crs=crs)
        answers: list[dict] = []
        failed: list[tuple[list[Polygon], ExternalSourceError]] = []
        for group in groups:
            ok, bad = _solve(ctx, group)
            answers += ok
            failed += bad
    logger.info('worldpop_done groups=%s answered=%s failed=%s requests=%s vertices=%s seconds=%.1f',
                len(groups), len(answers), len(failed), ctx.requests, prepared.report['vertices_after'],
                clock() - started)

    total_area = sum(p.area for p in parts) or 1.0
    covered = sum(a['_area'] for a in answers)
    coverage = covered / total_area * 100.0
    failures = [{'code': e.code, 'message': e.message, 'parts': len(g),
                 'http_status': (e.details or {}).get('http_status') if isinstance(e.details, dict) else None}
                for g, e in failed]
    if failed and (not answers or coverage < settings.worldpop_min_partial_coverage_pct):
        first = failed[0][1]
        raise ExternalSourceError(first.message, code=first.code, status_code=first.status_code,
                                  details={**(first.details if isinstance(first.details, dict) else {}),
                                           'chunks': len(groups), 'chunks_failed': len(failed),
                                           'coverage_pct': round(coverage, 1)})
    total = sum(a['total'] for a in answers)
    years = {a.get('data_year') for a in answers if a.get('data_year')}
    sources = {a.get('data_source') for a in answers if a.get('data_source')}
    result = PopulationResult(
        estimate=round(total, 1), year=settings.worldpop_year, resolution=settings.worldpop_resolution,
        dataset=DATASET_LABEL, api_version='v3', task_id=None,
        analysis_area_ha=round(total_area / 10_000.0, 2), simplification=prepared.report,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        partial=bool(failed), chunks=len(groups), chunks_failed=len(failed), parts=prepared.report['parts'],
        coverage_pct=round(coverage, 1), failures=failures,
        data_year=int(next(iter(years))) if len(years) == 1 else None,
        data_source=str(next(iter(sources))) if len(sources) == 1 else None,
        processing_time_ms=round(sum(float(a['processing_time_ms']) for a in answers
                                     if isinstance(a.get('processing_time_ms'), (int, float))), 1) or None,
        request_count=ctx.requests)
    if not failed:
        _cache.set(cache_key, result, settings.worldpop_cache_ttl_seconds)    # a PARTIAL result is never cached
    return result
