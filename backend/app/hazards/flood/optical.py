"""Sentinel-2 true-colour context images: port of ``gimagest`` of the reference script.

They are DISPLAY ONLY (the reference script never uses them to detect water). They help a human compare the SAR detection
with what the optical image shows when the sky was clear enough.
"""
from __future__ import annotations

import ee

MAX_CLOUD_PROBABILITY = 50
BANDS = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12']
TRUE_COLOR_VIS = {'min': 0, 'max': 0.4, 'bands': ['B8', 'B11', 'B4']}      # ``trueColorVis`` in the script


def _mask_s2_clouds(image: ee.Image) -> ee.Image:
    qa = image.select('QA60')
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return image.updateMask(mask).divide(10000).copyProperties(image, ['system:time_start'])


def _mask_with_probability(img: ee.Image) -> ee.Image:
    clouds = ee.Image(img.get('cloud_mask')).select('probability')
    return img.updateMask(clouds.lt(MAX_CLOUD_PROBABILITY))


def s2_context_image(aoi: ee.Geometry, start: str, end: str) -> ee.Image:
    sr = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterDate(start, end)
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50)).filterBounds(aoi).map(_mask_s2_clouds))
    probability = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
                   .filter(ee.Filter.And(ee.Filter.bounds(aoi), ee.Filter.date(start, end))))
    joined = ee.Join.saveFirst('cloud_mask').apply(
        primary=sr, secondary=probability,
        condition=ee.Filter.equals(leftField='system:index', rightField='system:index'))
    masked = ee.ImageCollection(joined).map(_mask_with_probability)
    return masked.median().clip(aoi).select(BANDS)
