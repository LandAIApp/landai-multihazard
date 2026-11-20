"""Otsu threshold: port of ``otsuThreshold`` / ``_otsuFromHist`` of the reference script (no behavioural change)."""
from __future__ import annotations

import ee

FALLBACK_THRESHOLD = -0.3        # ``var fallback = ee.Number(-0.3)``
MAX_BUCKETS = 256


def _otsu_from_hist(h: ee.Dictionary) -> ee.Number:
    counts = ee.Array(h.get('histogram'))
    means = ee.Array(h.get('bucketMeans'))

    size = means.length().get([0])
    total = counts.reduce(ee.Reducer.sum(), [0]).get([0])
    total_sum = means.multiply(counts).reduce(ee.Reducer.sum(), [0]).get([0])
    mean = ee.Number(total_sum).divide(total)

    def between_class_variance(i):
        i = ee.Number(i)
        c1 = counts.slice(0, 0, i)
        c2 = counts.slice(0, i, size)
        s1 = ee.Number(c1.reduce(ee.Reducer.sum(), [0]).get([0]))
        s2 = ee.Number(c2.reduce(ee.Reducer.sum(), [0]).get([0]))
        w1 = s1.divide(total)
        w2 = s2.divide(total)
        m1 = ee.Number(means.slice(0, 0, i).multiply(c1).reduce(ee.Reducer.sum(), [0]).get([0])).divide(s1.max(1))
        m2 = ee.Number(means.slice(0, i, size).multiply(c2).reduce(ee.Reducer.sum(), [0]).get([0])).divide(s2.max(1))
        return w1.multiply(m1.subtract(mean).pow(2)).add(w2.multiply(m2.subtract(mean).pow(2)))

    # possible thresholds: 1 .. size-1 (index of the first bucket of the upper class)
    bcv = ee.Array(ee.List.sequence(1, ee.Number(size).subtract(1)).map(between_class_variance))
    idx = ee.Number(bcv.argmax().get(0)).add(1)        # +1: the sequence starts at 1
    return ee.Number(means.get([idx]))


def otsu_threshold(image: ee.Image, region: ee.Geometry, scale: float, tile_scale: int = 4):
    """Histogram of the first band over ``region`` and the Otsu threshold (fallback -0.3 when there is no histogram)."""
    band = ee.String(image.bandNames().get(0))
    hist = image.reduceRegion(
        reducer=ee.Reducer.histogram(maxBuckets=MAX_BUCKETS), geometry=region, scale=scale,
        bestEffort=True, maxPixels=1e13, tileScale=tile_scale)
    h = ee.Dictionary(hist.get(band))
    return ee.Algorithms.If(h, _otsu_from_hist(h), ee.Number(FALLBACK_THRESHOLD))


def otsu_numpy(bucket_means, counts) -> float:
    """Pure-python twin of the same recipe, used by the unit tests to pin the arithmetic (not used at runtime)."""
    import numpy as np
    means = np.asarray(bucket_means, dtype=float)
    cnt = np.asarray(counts, dtype=float)
    size, total = len(means), cnt.sum()
    mean = (means * cnt).sum() / total
    best_i, best = 1, -1.0
    for i in range(1, size):
        s1, s2 = cnt[:i].sum(), cnt[i:].sum()
        w1, w2 = s1 / total, s2 / total
        m1 = (means[:i] * cnt[:i]).sum() / max(s1, 1)
        m2 = (means[i:] * cnt[i:]).sum() / max(s2, 1)
        bcv = w1 * (m1 - mean) ** 2 + w2 * (m2 - mean) ** 2
        if bcv > best:
            best, best_i = bcv, i
    return float(means[best_i])
