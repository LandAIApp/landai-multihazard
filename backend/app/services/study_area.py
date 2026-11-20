"""Study area (municipality or drawn polygon) shared by every hazard except the legacy wildfire path.

The wildfire services keep their own (identical) resolution code untouched; new hazards use this module so the AOI
handling is written once. Nothing here depends on a hazard.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import ee
from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry

from ..core.config import Settings, get_settings
from ..core.earth_engine import evaluate
from ..core.errors import MunicipalityNotFoundError
from ..schemas.common import AreaSelection, Notice
from . import administrative, aoi as aoi_service


@dataclass
class StudyArea:
    kind: str                          # 'municipality' | 'drawn'
    geometry: ee.Geometry
    hectares: float
    boundary: dict
    bounds: list[list[float]]
    department: str | None = None
    municipality: str | None = None
    ring: list[list[float]] | None = None


def _notice(code: str, message: str, **params) -> Notice:
    return Notice(code=code, message=message, params=params)


def preflight_area(area: AreaSelection, settings: Settings | None = None
                   ) -> tuple[float | None, list[Notice], list[Notice], object | None]:
    """Returns ``(hectares, blocking, warnings, handle)``.

    ``handle`` is the drawn ring (drawn) or the municipality FeatureCollection (municipality) so the caller does not
    resolve the area twice. Drawn polygons are validated locally first: an invalid or oversized area never costs an
    Earth Engine call.
    """
    settings = settings or get_settings()
    if area.geometry is not None:
        ring, hectares, blocking, warnings = aoi_service.check_drawn(area, settings)  # type: ignore[arg-type]
        return hectares, _from_issues(blocking), _from_issues(warnings), ring
    collection = administrative.select_municipality(area.department, area.municipality)
    info = evaluate(ee.Dictionary({'matches': collection.size(),
                                   'area_ha': collection.geometry().area(100).divide(10000)}),
                    'resolving the municipality')
    if not info or not info.get('matches'):
        return None, [_notice('municipality_not_found',
                              f"Municipality '{area.municipality}' was not found in department '{area.department}'.")], [], None
    hectares = float(info.get('area_ha') or 0)
    blocking: list[Notice] = []
    warnings: list[Notice] = []
    if hectares > settings.max_aoi_hectares:
        blocking.append(_notice('aoi_too_large',
                                f'The municipality covers {hectares:,.0f} ha, above the configured limit of '
                                f'{settings.max_aoi_hectares:,.0f} ha.', hectares=hectares, max=settings.max_aoi_hectares))
    elif hectares > settings.warn_aoi_hectares:
        warnings.append(_notice('aoi_large', f'Large area ({hectares:,.0f} ha): processing may be slow or hit limits.',
                                hectares=hectares))
    return hectares, blocking, warnings, collection


def _from_issues(issues) -> list[Notice]:
    return [Notice(code=i.code, message=i.message, params=dict(i.params)) for i in issues]


def build(area: AreaSelection, hectares: float, handle) -> StudyArea:
    """Earth Engine geometry + display boundary for an area that already passed ``preflight_area``."""
    if area.geometry is not None:
        drawn = aoi_service.build_drawn(handle, hectares)
        return StudyArea(kind='drawn', geometry=drawn.geometry, hectares=hectares, boundary=drawn.boundary,
                         bounds=drawn.bounds, ring=handle)
    boundary = administrative.boundary_geojson(handle)
    return StudyArea(kind='municipality', geometry=handle.geometry(), hectares=hectares, boundary=boundary,
                     bounds=administrative.geometry_bounds(boundary['geometry']),
                     department=area.department, municipality=area.municipality)


def from_context(ctx: dict) -> tuple[ee.Geometry, tuple[float, float, float, float] | None, BaseGeometry | None]:
    """(ee geometry, lon/lat bounds if known, municipal outline for tile skipping) from an exposure analysis context."""
    if ctx['kind'] == 'drawn':
        drawn = aoi_service.build_drawn(ctx['ring'], ctx['aoi_hectares'])
        return drawn.geometry, tuple(ctx['ring_bounds']), Polygon(ctx['ring'])
    collection = administrative.select_municipality(ctx['department'], ctx['municipality'])
    outline = None
    try:   # only used to skip download tiles outside the municipality: an optimisation, never required
        outline = shape(administrative.boundary_geojson(collection)['geometry'])
    except Exception:  # noqa: BLE001
        outline = None
    return collection.geometry(), None, outline


def geometry_bounds_lonlat(geometry: ee.Geometry) -> tuple[float, float, float, float]:
    ring = evaluate(geometry.bounds(), 'reading the study-area extent')['coordinates'][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)
