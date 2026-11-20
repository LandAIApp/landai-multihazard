"""Hazard footprint extraction for the Exposure module.

Method (chosen after comparing the alternatives, see docs/exposure-methodology.md):

* The footprint is the EXACT final cleaned burn mask (burn035..burn085 from the unchanged V7.6 graph),
  rasterised ONCE at the analysis scale (20 m) on a UTM grid with ``getDownloadURL`` (single multi-band
  GeoTIFF, bounded by EXPOSURE_MAX_PIXELS) and vectorised locally with rasterio (pixel-exact, 8-connected,
  no simplification). ``reduceToVectors`` is never used: it is unbounded for fragmented masks.
* The AOI polygon used to filter OSM is the exact drawn polygon, or, for a municipality, the 20 m
  raster of the municipal geometry (boundary deviates by less than one pixel from the vector).
* Lengths/areas are computed in the same UTM CRS as the raster.
"""
from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field

import ee
import httpx
import numpy as np
import rasterio
import rasterio.features
from rasterio.io import MemoryFile
from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..core.config import Settings
from ..core.earth_engine import ensure_initialized, map_ee_error
from ..core.errors import ExposureAreaTooLargeError, FootprintError, WildfireError
from ..wildfire.config import AREA_SCALE, MIN_CONNECTED_PIXELS, THRESHOLD_SPECS
from . import spatial

logger = logging.getLogger('landai.exposure')

AOI_BAND = 'AOI'
# postprocessing.py keeps pixels whose 8-connected component has >= MIN_CONNECTED_PIXELS pixels. Deciding that for a
# pixel only needs the pixels within MIN_CONNECTED_PIXELS - 1 steps of it, so each tile is requested with twice that
# margin (12 px = 240 m) and cropped back: components that cross a tile border are measured exactly.
TILE_MARGIN_PX = 2 * MIN_CONNECTED_PIXELS
# mask key (burn050) -> (threshold, area key wf050, band name Burn050)
THRESHOLD_BY_KEY = {key: (t, area_key, band) for t, key, area_key, band in THRESHOLD_SPECS}


@dataclass
class Footprint:
    """Footprints and AOI in a metric CRS (``crs``), plus raster provenance."""

    crs: str
    pixel_size_m: float
    aoi: BaseGeometry
    footprints: dict[str, BaseGeometry]            # mask key -> geometry (metric CRS)
    pixel_counts: dict[str, int] = field(default_factory=dict)
    source: str = 'wildfire_analysis'              # | user_supplied
    grid: dict = field(default_factory=dict)       # provenance: transform, shape, crs
    aoi_from_raster: bool = False

    def area_ha(self, key: str) -> float:
        return spatial.area_ha(self.footprints[key])


def estimate_pixels(bounds: tuple[float, float, float, float], crs: str, scale: float = AREA_SCALE) -> int:
    width, height = spatial.projected_bbox_size(bounds, crs)
    return int(np.ceil(width / scale) * np.ceil(height / scale))


def vectorize(array: np.ndarray, transform) -> BaseGeometry:
    """Union of the connected components of a 0/1 raster (pixel-exact, 8-connected, no simplification)."""
    mask = (array > 0).astype('uint8')
    if not mask.any():
        return Polygon()
    parts = [shape(geom) for geom, value in rasterio.features.shapes(mask, mask=mask.astype(bool),
                                                                      transform=transform, connectivity=8)
             if value == 1]
    return unary_union(parts) if len(parts) > 1 else parts[0]


def read_download(content: bytes, band_names: list[str]) -> tuple[dict[str, np.ndarray], object, str]:
    """Parse the Earth Engine download: a multi-band GeoTIFF, or a zip with one GeoTIFF per band."""
    if content[:2] == b'PK':
        arrays: dict[str, np.ndarray] = {}
        transform, crs = None, ''
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.namelist():
                if not member.lower().endswith(('.tif', '.tiff')):
                    continue
                name = next((b for b in band_names if f'.{b}.' in member or member.endswith(f'{b}.tif')), None)
                if name is None:
                    continue
                with MemoryFile(archive.read(member)) as mem, mem.open() as src:
                    arrays[name] = src.read(1)
                    transform, crs = src.transform, str(src.crs)
        missing = [b for b in band_names if b not in arrays]
        if missing:
            raise FootprintError('The Earth Engine download did not contain all requested bands.',
                                 details={'missing': missing})
        return arrays, transform, crs
    with MemoryFile(content) as mem, mem.open() as src:
        if src.count != len(band_names):
            raise FootprintError('The Earth Engine download has an unexpected number of bands.',
                                 details={'expected': len(band_names), 'found': src.count})
        data = src.read()
        return ({name: data[i] for i, name in enumerate(band_names)}, src.transform, str(src.crs))


def _download_error_details(response: httpx.Response) -> dict:
    """HTTP status plus Earth Engine's own explanation (the download endpoint answers 4xx with a JSON/text
    body such as 'Computation timed out.' or 'Total request size ... must be less than ...')."""
    details: dict = {'http_status': response.status_code}
    try:
        body = response.read()[:2000].decode('utf-8', errors='replace')
    except httpx.HTTPError:
        body = ''
    message = body.strip()
    try:
        import json
        payload = json.loads(body)
        if isinstance(payload, dict):
            err = payload.get('error')
            message = (err.get('message') if isinstance(err, dict) else err) or message
    except ValueError:
        pass
    if message:
        details['earth_engine_message'] = str(message)[:500]
    logger.warning('footprint_download_rejected status=%s message=%s', response.status_code, message[:500])
    return details


def _download(url: str, settings: Settings) -> bytes:
    limit = 60_000_000
    chunks, size = [], 0
    try:
        with httpx.stream('GET', url, timeout=settings.exposure_download_timeout_s,
                          follow_redirects=True) as response:
            if response.status_code != 200:
                raise FootprintError('Earth Engine could not deliver the footprint raster.',
                                     details=_download_error_details(response))
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise FootprintError('The footprint raster is larger than the allowed size. Use a smaller area.')
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise FootprintError('The footprint raster download failed.', details=type(exc).__name__) from exc
    return b''.join(chunks)


@dataclass
class TilePlan:
    single: bool
    x0: float = 0.0            # canvas origin (metric CRS): west edge
    y1: float = 0.0            # canvas origin: north edge
    width: int = 0             # canvas size in pixels
    height: int = 0
    tiles: list[tuple[int, int, int, int]] = field(default_factory=list)   # core (col0, col1, row0, row1)


def plan_tiles(bounds: tuple[float, float, float, float], crs: str, tile_px: int,
               scale: float = AREA_SCALE) -> TilePlan:
    """Split the AOI bounding box into square tiles of at most ``tile_px`` pixels per side.

    Earth Engine evaluates a download request in memory as a whole (the area statistics use tileScale for that
    reason), so a municipality-sized request fails with 'User memory limit exceeded'. Several smaller requests
    keep each evaluation small; the grid is anchored on multiples of ``scale`` so tiles line up exactly.
    """
    width_m, height_m = spatial.projected_bbox_size(bounds, crs)
    if np.ceil(width_m / scale) <= tile_px and np.ceil(height_m / scale) <= tile_px:
        return TilePlan(single=True)
    west, south, east, north = bounds
    t = spatial._transformer(spatial.WGS84, crs)
    xs, ys = zip(*[t.transform(x, y) for x, y in ((west, south), (east, south), (east, north), (west, north))])
    x0 = float(np.floor(min(xs) / scale) * scale)
    y1 = float(np.ceil(max(ys) / scale) * scale)
    width = int(np.ceil((max(xs) - x0) / scale))
    height = int(np.ceil((y1 - min(ys)) / scale))
    tiles = [(c, min(c + tile_px, width), r, min(r + tile_px, height))
             for r in range(0, height, tile_px) for c in range(0, width, tile_px)]
    return TilePlan(single=False, x0=x0, y1=y1, width=width, height=height, tiles=tiles)


def _tile_region(plan: TilePlan, tile: tuple[int, int, int, int], crs: str, scale: float = AREA_SCALE,
                 margin_px: int = TILE_MARGIN_PX):
    c0, c1, r0, r1 = tile
    m = margin_px
    xmin, xmax = plan.x0 + (c0 - m) * scale, plan.x0 + (c1 + m) * scale
    ymax, ymin = plan.y1 - (r0 - m) * scale, plan.y1 - (r1 + m) * scale
    return ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], crs, False)


def _paste(canvas: dict[str, np.ndarray], arrays: dict[str, np.ndarray], transform, plan: TilePlan,
           tile: tuple[int, int, int, int], scale: float = AREA_SCALE) -> None:
    """Copy the CORE of a downloaded tile (margin dropped) into the canvas, checking grid alignment."""
    col_off = (transform.c - plan.x0) / scale
    row_off = (plan.y1 - transform.f) / scale
    if (abs(col_off - round(col_off)) > 0.05 or abs(row_off - round(row_off)) > 0.05
            or abs(abs(transform.a) - scale) > 1e-6 or abs(abs(transform.e) - scale) > 1e-6):
        raise FootprintError('Earth Engine returned a raster tile on an unexpected pixel grid.',
                             details={'col_offset': col_off, 'row_offset': row_off, 'pixel': float(transform.a)})
    col_off, row_off = int(round(col_off)), int(round(row_off))
    c0, c1, r0, r1 = tile
    any_band = next(iter(arrays.values()))
    h, w = any_band.shape
    gc0, gc1 = max(c0, col_off), min(c1, col_off + w)
    gr0, gr1 = max(r0, row_off), min(r1, row_off + h)
    if gc0 >= gc1 or gr0 >= gr1:
        return
    for name, array in arrays.items():
        canvas[name][gr0:gr1, gc0:gc1] = array[gr0 - row_off:gr1 - row_off, gc0 - col_off:gc1 - col_off]


def _fetch_tiles(plan: TilePlan, fetch, all_names: list[str], crs: str, settings: Settings,
                 aoi_metric: BaseGeometry | None, scale: float = AREA_SCALE, margin_px: int = TILE_MARGIN_PX):
    """Download every tile and stitch the cores into one raster on the canvas grid.

    The FIRST tile runs alone: Earth Engine caches intermediate results (the trained Random Forest, the
    composites), so the remaining tiles - run a few in parallel - can reuse them instead of recomputing.
    Tiles that do not touch the AOI are skipped. A time budget stops scheduling new tiles.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from rasterio.transform import from_origin

    canvas = {n: np.zeros((plan.height, plan.width), dtype='uint8') for n in all_names}
    zone = aoi_metric.buffer(10 * scale) if aoi_metric is not None else None   # boundary is simplified (100 m)
    work = []
    for index, tile in enumerate(plan.tiles):
        c0, c1, r0, r1 = tile
        if zone is not None:
            box_m = Polygon.from_bounds(plan.x0 + c0 * scale, plan.y1 - r1 * scale,
                                        plan.x0 + c1 * scale, plan.y1 - r0 * scale)
            if not zone.intersects(box_m):
                continue
        work.append((index, tile))
    started = time.monotonic()
    deadline = started + float(settings.exposure_max_seconds)
    logger.info('footprint_tiles total=%s requested=%s canvas=%sx%s workers=%s', len(plan.tiles), len(work),
                plan.width, plan.height, settings.exposure_tile_workers)

    def _is_memory_error(exc: Exception) -> bool:
        d = getattr(exc, 'details', None)
        msg = str(d.get('earth_engine_message', '')) if isinstance(d, dict) else ''
        status = d.get('http_status') if isinstance(d, dict) else None
        return 'memory' in msg.lower() or (status == 503 and 'capacity' in msg.lower())

    def run_one(index, tile):
        t0 = time.monotonic()
        # the wildfire grid (20 m, default margin) is passed through the original call signature
        region = (_tile_region(plan, tile, crs) if (scale, margin_px) == (AREA_SCALE, TILE_MARGIN_PX)
                  else _tile_region(plan, tile, crs, scale, margin_px))
        arrays, transform, tile_crs = fetch({'region': region})
        logger.info('footprint_tile %s/%s done in %.1f s (%.0f s elapsed)', index + 1, len(plan.tiles),
                    time.monotonic() - t0, time.monotonic() - started)
        return tile, arrays, transform, tile_crs

    def run_split(index, tile, depth=0):
        """Run a tile; if Earth Engine runs out of memory, retry it as four smaller quadrants (up to 2 levels)."""
        if time.monotonic() >= deadline:
            raise FootprintError('The exposure computation exceeded its time budget. Use a smaller area.',
                                 details={'tile': f'{index + 1}/{len(plan.tiles)}',
                                          'max_seconds': settings.exposure_max_seconds})
        try:
            return [run_one(index, tile)]
        except WildfireError as exc:
            c0, c1, r0, r1 = tile
            if _is_memory_error(exc) and depth < 2 and min(c1 - c0, r1 - r0) >= 160:
                cm, rm = (c0 + c1) // 2, (r0 + r1) // 2
                logger.warning('footprint_tile_split tile=%s/%s depth=%s reason=earth_engine_memory', index + 1,
                               len(plan.tiles), depth + 1)
                out = []
                for sub in ((c0, cm, r0, rm), (cm, c1, r0, rm), (c0, cm, rm, r1), (cm, c1, rm, r1)):
                    out.extend(run_split(index, sub, depth + 1))
                return out
            if isinstance(exc.details, dict):
                exc.details['tile'] = f'{index + 1}/{len(plan.tiles)}'
            raise

    def run(item):
        index, tile = item
        return run_split(index, tile)

    def place(results):
        for tile, arrays, transform, tile_crs in results:
            if tile_crs and tile_crs.upper() != crs.upper():
                raise FootprintError('Earth Engine returned a tile in an unexpected CRS.',
                                     details={'expected': crs, 'found': tile_crs})
            _paste(canvas, arrays, transform, plan, tile) if scale == AREA_SCALE else _paste(
                canvas, arrays, transform, plan, tile, scale)

    if work:
        place(run(work[0]))
    workers = max(1, int(settings.exposure_tile_workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(run, work[1:]):
            place(result)
    return canvas, from_origin(plan.x0, plan.y1, scale, scale), crs


def extract_from_earth_engine(result: dict, aoi: ee.Geometry, bounds: tuple[float, float, float, float],
                              mask_keys: list[str], settings: Settings,
                              aoi_metric: BaseGeometry | None = None,
                              aoi_wgs84: BaseGeometry | None = None,
                              downloader=_download) -> Footprint:
    """Wildfire entry point: rasterise the requested cleaned burn masks (and the AOI) once and vectorise them.

    ``result`` is the dictionary returned by run_burn_model (unchanged scientific graph).
    ``bounds`` = (west, south, east, north) of the AOI. ``aoi_metric`` is the exact AOI in the UTM CRS
    when it is known locally (drawn polygons); otherwise it is reconstructed from the AOI raster band.
    """
    masks = {k: (result.get(k), THRESHOLD_BY_KEY[k][2]) for k in mask_keys}   # presence checked after the size limit
    return extract_masks(masks, aoi, bounds, settings, aoi_metric=aoi_metric, aoi_wgs84=aoi_wgs84,
                         downloader=downloader, scale=AREA_SCALE, margin_px=TILE_MARGIN_PX,
                         max_pixels=settings.exposure_max_pixels, what='affected-area')


def extract_masks(masks: dict[str, tuple[ee.Image, str]], aoi: ee.Geometry,
                  bounds: tuple[float, float, float, float], settings: Settings, *,
                  scale: float, margin_px: int, max_pixels: int,
                  aoi_metric: BaseGeometry | None = None, aoi_wgs84: BaseGeometry | None = None,
                  downloader=_download, what: str = 'footprint') -> Footprint:
    """Hazard-independent core: ``masks`` maps a footprint key to ``(ee.Image mask, band name)``.

    Every mask is rasterised ONCE on a UTM grid at ``scale`` metres (tiled when the area is large; each tile carries a
    ``margin_px`` margin so a connected-pixel filter that crosses a tile border is evaluated exactly) and vectorised
    locally. ``margin_px`` must be at least twice the connected-pixel threshold of the hazard's own cleaning step.
    """
    west, south, east, north = bounds
    crs = spatial.utm_epsg((west + east) / 2, (south + north) / 2)
    pixels = estimate_pixels(bounds, crs, scale)
    if pixels > max_pixels:
        raise ExposureAreaTooLargeError(
            f'The analysis area spans {pixels:,} pixels at {scale:g} m, above the exposure limit of '
            f'{max_pixels:,}. Use a smaller area.',
            details={'pixels': pixels, 'max_pixels': max_pixels, 'scale_m': scale})

    mask_keys = list(masks)
    missing = [k for k in mask_keys if masks[k][0] is None]
    if missing:
        raise FootprintError('The analysis did not produce the requested masks.', details={'missing': missing})
    names = [masks[k][1] for k in mask_keys]
    bands = [masks[k][0].unmask(0).toByte().rename(masks[k][1]) for k in mask_keys]
    bands.append(ee.Image.constant(1).clip(aoi).unmask(0).toByte().rename(AOI_BAND))
    image = ee.Image.cat(bands)
    ensure_initialized()
    all_names = names + [AOI_BAND]
    plan = plan_tiles(bounds, crs, settings.exposure_tile_px, scale)

    def fetch(region_params: dict) -> tuple[dict[str, np.ndarray], object, str]:
        try:
            url = image.getDownloadURL({**region_params, 'crs': crs, 'scale': scale,
                                        'format': 'GEO_TIFF', 'filePerBand': False})
        except ee.EEException as exc:
            raise map_ee_error(exc, f'preparing the {what} raster') from exc
        except WildfireError:
            raise
        return read_download(downloader(url, settings), all_names)

    if plan.single:
        # small area: one request over the AOI bounding box (no margins needed, nothing to stitch)
        region = ee.Geometry.Rectangle([west, south, east, north], None, False)
        arrays, transform, file_crs = fetch({'region': region})
    else:
        skip_aoi = aoi_metric
        if skip_aoi is None and aoi_wgs84 is not None:
            skip_aoi = spatial.to_metric(aoi_wgs84, crs)
        grid = () if (scale, margin_px) == (AREA_SCALE, TILE_MARGIN_PX) else (scale, margin_px)
        arrays, transform, file_crs = _fetch_tiles(plan, fetch, all_names, crs, settings, skip_aoi, *grid)
    if file_crs and file_crs.upper() != crs.upper():
        # keep the raster's own CRS as the metric CRS (it is projected); never assume
        crs = file_crs
    footprints, counts = {}, {}
    for key, band in zip(mask_keys, names):
        footprints[key] = vectorize(arrays[band], transform)
        counts[key] = int((arrays[band] > 0).sum())
    from_raster = aoi_metric is None
    aoi_geom = aoi_metric if aoi_metric is not None else vectorize(arrays[AOI_BAND], transform)
    return Footprint(
        crs=crs, pixel_size_m=float(abs(transform.a)), aoi=aoi_geom, footprints=footprints,
        pixel_counts=counts, aoi_from_raster=from_raster,
        grid={'crs': crs, 'transform': [float(v) for v in tuple(transform)[:6]],
              'shape': list(next(iter(arrays.values())).shape), 'requested_scale_m': scale})


def from_geometries(hazard_wgs84: BaseGeometry, aoi_wgs84: BaseGeometry, key: str = 'user') -> Footprint:
    """Externally supplied hazard polygon (separate input mode, NOT the validated wildfire workflow)."""
    c = aoi_wgs84.centroid
    crs = spatial.utm_epsg(c.x, c.y)
    return Footprint(crs=crs, pixel_size_m=0.0, aoi=spatial.to_metric(aoi_wgs84, crs),
                     footprints={key: spatial.to_metric(hazard_wgs84, crs)}, source='user_supplied')
