"""Sentinel-1 flood detection graph: a line-by-line port of ``docs/flood/flood_gee_reference.js``.

What is ported (and where it comes from in the reference script):

* ``getS1Composite``  -> :func:`s1_composite`  (COPERNICUS/S1_GRD, IW, VV+VH, DESCENDING, median, clip,
  ``focal_median`` radius 30 m on VV and VH separately).
* ``lrVV / lrVH / lrCombined`` -> :func:`log_ratios`  (``lrCombined = min(lrVV, lrVH)``).
* ``otsuThreshold`` -> :mod:`.otsu`  (256 buckets, bestEffort, fallback -0.3).
* ``floodMask = lrCombined.lte(thr).selfMask()`` then ``connectedPixelCount(100, true) >= 20`` -> :func:`flood_masks`.

What is NOT ported on purpose, because the reference script does not apply it either:

* the slope mask (``maxSlopeDeg = 5``, SRTM): defined in the script but the ``updateMask(slopeMask)`` call is commented out;
* the Sentinel-2 composites: used only for display in the script (see :mod:`.optical`), never for detection;
* the Drive export (``Export.image.toDrive``).

Non-scientific differences, all documented in docs/flood/methodology.md: ``tileScale`` on the reduceRegion calls (changes
memory use, never a value) and no ``getInfo()`` inside the graph (the script's ``print(...getInfo())`` calls are replaced by
one evaluation of a small dictionary at the API boundary).
"""
from __future__ import annotations

import ee

from .otsu import otsu_threshold

S1_COLLECTION = 'COPERNICUS/S1_GRD'
SPECKLE_RADIUS_M = 30            # focal_median radius, meters
OTSU_SCALE_M = 10                # ``var scale = 10`` in the script
MIN_CONN_PIXELS = 20             # ``var minConnPixels = 20``
CONN_MAX_SIZE = 100              # ``connectedPixelCount(100, true)``
MASK_SCALE_M = 10
MAX_PIXELS = 1e13


def s1_collection(aoi: ee.Geometry, start: str, end: str) -> ee.ImageCollection:
    """The exact filter chain of ``getS1Composite``. ``end`` is exclusive (``filterDate``)."""
    return (ee.ImageCollection(S1_COLLECTION)
            .filterBounds(aoi)
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
            .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
            .filterDate(start, end))


def s1_composite(aoi: ee.Geometry, start: str, end: str) -> ee.Image:
    """Median composite (on the dB values delivered by COPERNICUS/S1_GRD), clipped, speckle-filtered per band."""
    colmed = ee.Image(s1_collection(aoi, start, end).median()).clip(aoi)
    vv = colmed.select('VV').focal_median(SPECKLE_RADIUS_M, 'circle', 'meters').rename('VV')
    vh = colmed.select('VH').focal_median(SPECKLE_RADIUS_M, 'circle', 'meters').rename('VH')
    return vv.addBands(vh)


def to_linear(img: ee.Image) -> ee.Image:
    """``toLinear`` of the script: dB -> linear power."""
    return ee.Image(10).pow(img.divide(10))


def log_ratios(pre: ee.Image, post: ee.Image, ratio_domain: str = 'linear') -> dict[str, ee.Image]:
    """Temporal change per polarisation and their minimum.

    ``linear`` (default): ``toLinear`` first; ``log10(post/pre)`` equals the dB difference divided by 10, so a flood
                   (backscatter drop) gives a NEGATIVE value, matching the ``lte(threshold)`` mask.
    ``reference``: ``post.divide(pre).log10()`` on the raw dB values (the script's active lines); the sign is inverted.
    """
    if ratio_domain == 'linear':
        lr_vv = to_linear(post.select('VV')).divide(to_linear(pre.select('VV'))).log10().rename('lrVV')
        lr_vh = to_linear(post.select('VH')).divide(to_linear(pre.select('VH'))).log10().rename('lrVH')
    else:
        lr_vv = post.select('VV').divide(pre.select('VV')).log10().rename('lrVV')
        lr_vh = post.select('VH').divide(pre.select('VH')).log10().rename('lrVH')
    return {'lrVV': lr_vv, 'lrVH': lr_vh, 'lrCombined': lr_vv.min(lr_vh).rename('lrCombined')}


def flood_masks(lr_combined: ee.Image, aoi: ee.Geometry, tile_scale: int = 4) -> dict:
    """Otsu threshold, raw mask and the cleaned mask (connected-pixel filter)."""
    thr = ee.Number(otsu_threshold(lr_combined, aoi, OTSU_SCALE_M, tile_scale))
    raw = lr_combined.lte(thr).selfMask()
    conn = raw.connectedPixelCount(CONN_MAX_SIZE, True)
    final = raw.updateMask(conn.gte(MIN_CONN_PIXELS))
    return {'threshold': thr, 'raw': raw, 'final': final}


def flood_graph(aoi: ee.Geometry, pre_start: str, pre_end: str, post_start: str, post_end: str,
                ratio_domain: str = 'linear', tile_scale: int = 4) -> dict:
    """Every server-side object the engine needs (nothing is evaluated here)."""
    pre = s1_composite(aoi, pre_start, pre_end)
    post = s1_composite(aoi, post_start, post_end)
    lr = log_ratios(pre, post, ratio_domain)
    masks = flood_masks(lr['lrCombined'], aoi, tile_scale)
    return {'pre': pre, 'post': post, **lr, **masks}


def statistics(graph: dict, aoi: ee.Geometry, tile_scale: int = 4) -> ee.Dictionary:
    """One small dictionary for a single evaluation: threshold + areas (hectares) of the cleaned and the raw mask."""
    def hectares(mask: ee.Image) -> ee.Number:
        area = mask.unmask(0).multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=MASK_SCALE_M, maxPixels=MAX_PIXELS, tileScale=tile_scale)
        return ee.Number(area.values().get(0)).divide(10000)
    return ee.Dictionary({
        'otsuThreshold': graph['threshold'],
        'floodHectares': hectares(graph['final']),
        'floodRawHectares': hectares(graph['raw']),
    })


def availability(aoi: ee.Geometry, pre_start: str, pre_end: str, post_start: str, post_end: str) -> ee.Dictionary:
    """Scene counts for the preflight (one tiny evaluation). Sentinel-2 counts are context only."""
    def s2(start: str, end: str) -> ee.Number:
        return (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(aoi).filterDate(start, end)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50)).size())
    return ee.Dictionary({
        's1_pre': s1_collection(aoi, pre_start, pre_end).size(),
        's1_post': s1_collection(aoi, post_start, post_end).size(),
        's2_pre': s2(pre_start, pre_end),
        's2_post': s2(post_start, post_end),
    })
