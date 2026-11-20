# Flood module — methodology and traceability

**Source of truth:** [`flood_gee_reference.js`](flood_gee_reference.js), the Google Earth Engine script supplied by Land AI,
copied verbatim. The module is a port of that script and **adds no science of its own**. Where the application had to add
something (date guards, memory handling), it is listed under "Application additions" and is **not** part of the method.

Status: **experimental · under validation**. No accuracy metric against reference flood maps has been computed.

## What the product is

A *detected inundation extent* (`product_type = potential_detection`) at 10 m, derived from the change in Sentinel-1 radar
backscatter between a PRE and a POST window. It is **not** water depth, a hydraulic simulation, a flood probability or a
damage assessment.

## Line-by-line mapping

| Reference script | Port (`backend/app/hazards/flood/`) |
|---|---|
| L94-113 `getS1Composite`: `COPERNICUS/S1_GRD`, `IW`, VV and VH, `DESCENDING`, date window, `median()`, `clip(aoi)`, `focal_median(radius 30 m)` on VV and VH separately | `s1.py` → `s1_collection`, `s1_composite` (`FOCAL_RADIUS_M = 30`) |
| L124-125 `lrVV`, `lrVH` = `log10(post / pre)` | `s1.py` → `log_ratios` (`ratio_domain='reference'`, comparison only) |
| L127-133 commented alternative: dB → linear power (`10^(x/10)`) before `log10(post / pre)` | `s1.py` → `log_ratios` (`ratio_domain='linear'`, **default**) |
| L136 `lrCombined = lrVV.min(lrVH)` | `s1.py` → `log_ratios` |
| L143-200 `otsuThreshold` / `_otsuFromHist`: 256-bucket histogram, `bestEffort`, `scale = 10`, fallback `-0.3`, between-class variance, `argmax().get(0)`, `means.get([idx + 1])` | `otsu.py` → `otsu_threshold`, `_otsu_from_hist`; `otsu_numpy` is a NumPy twin used only by the unit tests |
| L203 `scale = 10` | `s1.py` → `MASK_SCALE_M = 10` |
| L208 `floodMask = lrCombined.lte(thr).selfMask()` | `s1.py` → `flood_masks` |
| L211-217 slope mask (SRTM, 5°) — **the script keeps it disabled** (`//.updateMask(slopeMask)`) | **Not applied**, not computed |
| L219-221 `connectedPixelCount(100, true)` ≥ 20 px | `s1.py` → `MIN_CONNECTED_PIXELS = 20`, `MAX_CONNECTED_SIZE = 100` |
| L31-81 Sentinel-2 SR Harmonized + Cloud Probability composites | `optical.py` → **display-only** context layers (`s2_pre`, `s2_post`); they never enter the detection |
| L226-232 `Export.image.toDrive` | Replaced by the explicit "Analyze exposure" step (rasterise the same mask, then OSM + WorldPop) |

The offline test-suite builds the Earth Engine graph without credentials and asserts its structure
(`backend/tests/test_multihazard.py`): no SRTM, no slope and no Sentinel-2 in the detection graph; radius 30; scale 10;
connected pixels 100 / 20; `min(lrVV, lrVH)`; fallback `-0.3`.

## Finding that needs your decision: the ratio domain

`COPERNICUS/S1_GRD` in Earth Engine is **already in decibels** (negative values for most surfaces).

* The **active code** of the script divides the two dB values (`post / pre`) and then takes `log10`. With dB inputs that is a
  ratio of two negative numbers ≈ 1, so `log10` is a small number and its sign is *inverted*: a backscatter drop (water)
  makes `|post| > |pre|` and a **positive** value, whereas the script then selects `lrCombined <= threshold`.
* The **commented alternative** (L127-133) converts to linear power first. There, a backscatter drop gives
  `post/pre < 1` and a **negative** log-ratio, which is what `lte(threshold)` and the `-0.3` fallback assume.

The API still accepts `ratio_domain` (`reference` | `linear`) but the UI no longer offers it. The default is `linear`: the active dB-division of the script inverts the
sign (it flagged land and gave an inverted area in testing), so `reference` is kept only for comparison. The UI exposes the switch under *Advanced options*. Before the
module is called validated, run both variants on a known event and compare against the GEE Code Editor output (see
`docs/LOCAL_TESTING_ES.md`, section 8). The numbers behind this statement are asserted in
`test_ratio_domain_semantics`.

## Application additions (not part of the method)

* Date guards: no future POST window, nothing before `FLOOD_MIN_DATE` (2015-01-01, Sentinel-1 era), each window at most
  `FLOOD_MAX_WINDOW_DAYS` (90). They avoid wasted Earth Engine calls.
* `tileScale` (`FLOOD_TILE_SCALE`, default 4) on reductions, only to avoid Earth Engine memory errors. It does not change
  values.
* Warning `flood_extent_very_large` when the detected share exceeds 40 % of the study area. It is a heuristic to prompt a
  review of the dates and the log-ratio layer; it does not alter the result.
* Study-area limits and rate limits shared with the rest of the platform.

## Known limitations (also shown in the UI and in every export)

1. Under validation: no accuracy metrics.
2. DESCENDING passes only: one acquisition geometry.
3. No permanent-water mask; no slope mask (disabled in the script); no HAND / urban / vegetation handling.
4. SAR confusions: smooth surfaces (wet sand, pavement, radar shadow) lower the backscatter; flooded vegetation and urban
   areas can be under-detected.
5. The Otsu threshold depends on the study area and on the share that actually changed.
6. Exposure at 10 m is limited by the raster pixel budget (`FLOOD_EXPOSURE_MAX_PIXELS`, 6 M px ≈ 600 km²).
