"""Flood footprint for the shared Exposure engine: re-runs the deterministic flood graph for the parameters that the BACKEND
recorded in the signed analysis reference, and rasterises the cleaned mask at its native 10 m."""
from __future__ import annotations

from ...core.config import Settings
from ...services import footprint as footprint_service
from ...services import study_area
from ...services.footprint import Footprint
from . import s1

FOOTPRINT_KEY = 'flood'
BAND = 'Flood'
SCALE_M = s1.MASK_SCALE_M
# connected-pixel cleaning needs the pixels within MIN_CONN_PIXELS-1 steps; twice that is kept as margin per tile
MARGIN_PX = 2 * s1.MIN_CONN_PIXELS


def resolve_footprint(ctx: dict, settings: Settings) -> Footprint:
    from shapely.geometry import Polygon
    from ...services import spatial

    geometry, bounds_ll, outline = study_area.from_context(ctx)
    p = ctx['params']
    graph = s1.flood_graph(geometry, p['pre_start'], p['pre_end'], p['post_start'], p['post_end'],
                           p.get('ratio_domain', 'linear'), settings.flood_tile_scale)
    if bounds_ll is None:
        bounds_ll = study_area.geometry_bounds_lonlat(geometry)
    fp = footprint_service.extract_masks(
        {FOOTPRINT_KEY: (graph['final'], BAND)}, geometry, tuple(bounds_ll), settings,
        scale=SCALE_M, margin_px=MARGIN_PX, max_pixels=settings.flood_exposure_max_pixels,
        aoi_wgs84=outline, what='flood footprint')
    if ctx['kind'] == 'drawn':
        fp.aoi = spatial.to_metric(Polygon(ctx['ring']), fp.crs)     # exact drawn ring, same CRS as the raster
        fp.aoi_from_raster = False
    return fp
