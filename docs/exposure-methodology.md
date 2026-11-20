# Exposure & Impact – methodology

> **Exposure estimates are preliminary. Intersecting buildings, roads or population with a satellite-derived affected area does not confirm physical damage, casualties or displacement.**
> (ES: *Las estimaciones de exposición son preliminares. La intersección de edificios, vías o población con un área potencialmente afectada no confirma daños físicos, víctimas ni desplazamientos.*)

## 1. Vocabulary (kept distinct in API and UI)
| Term | Meaning |
|---|---|
| Study area (AOI) | Municipality or user-drawn polygon given to the V7.6 analysis |
| Affected area | Pixels of the V7.6 probability map ≥ threshold (default 0.72), keeping the V7.6 post-processing |
| Exposure geometry | Polygon rebuilt from those pixels (raster-first, 20 m, UTM) – the only geometry used for intersections |
| Exposed features | OSM buildings/roads/facilities intersecting the exposure geometry (and, separately, a proximity buffer) |
| Population | WorldPop estimate inside the exposure geometry – never the whole AOI |

The module runs **only** when the user presses "Analyze Exposure". It never uses the whole AOI as hazard.

## 2. Algorithm V7.6 and AOI dependency
V7.6 is unchanged. A drawn polygon only changes the geometry fed to it. The algorithm is AOI-dependent:
training samples (`sample(region=aoi, seed)`) and the Random Forest are fitted per AOI; area statistics are
reduced over the AOI; `connectedPixelCount` has edge effects at the AOI boundary; VIIRS seeds are restricted to
the AOI. Per-pixel composites (Sentinel-2, Dynamic World) are AOI-independent.
**Therefore a drawn polygon is not numerically equivalent to the municipality that contains it**, and no such
equivalence is claimed. Results must be reported together with the AOI that produced them.

## 3. Footprint
`analysis_ref` (HMAC-signed, expiring, issued by `/wildfire/analyze`) lets the backend re-run the deterministic
V7.6 graph, download the burn mask with `getDownloadURL` (GeoTIFF, 20 m, UTM), vectorise it with rasterio (8-connected,
no `reduceToVectors`), and report area consistency against the analysis area (warning if >2 % apart). Simplification
is applied only for display and WorldPop payloads and is always reported (vertices before/after, tolerance, area change).
Large areas are downloaded as tiles (`EXPOSURE_TILE_PX`, default 640 px + 12 px margin, cropped and stitched on the 20 m grid; the first tile runs alone so Earth Engine can cache the trained Random Forest, tiles outside the study area are skipped, and `EXPOSURE_MAX_SECONDS` bounds the total) because Earth Engine evaluates a download in memory (`User memory limit exceeded` otherwise); the margin is twice the 6-pixel minimum component size of the V7.6 cleaning, so components that cross a tile border are measured exactly. Resolutions: analysis/vectorisation 20 m; display geometry may be simplified; WorldPop 100 m or 1 km grid.

## 4. OpenStreetMap (Overpass)
POST with bbox (areas larger than ~9 km (1.5 cells of 6 km) are split into `OVERPASS_CELL_KM` cells, only those touching the buffered footprint, with a 1 s pause between requests, one cache entry per cell and de-duplication of ways returned by several cells; a single small bbox keeps the `out count` pre-check), `out count` pre-check against `OVERPASS_MAX_ELEMENTS`, `out tags geom`, descriptive User-Agent,
no retry on the same server; on 429/5xx/timeout the query is tried once on each mirror in `OVERPASS_FALLBACK_ENDPOINTS` (2 s pause), then the source is reported as an error, local exact intersection with shapely. Tag sets: `building=*`;
`highway=*` (motorway…track, `_link` merged into parent class); `amenity=hospital|clinic|doctors`, `healthcare=*`;
`amenity=school|kindergarten|college|university`. Relations are skipped and counted (warning `osm_relations_skipped`).
Roads: length of the union of geometries clipped to the footprint (no double counting). Facilities: a node inside a
polygon of the same class is dropped. A category with zero OSM features in the study area is
`null / coverage="no_osm_data"` – **never 0**. OSM completeness varies; absence of data is not absence of assets.
Buffer (default 500 m) is a proximity indicator, not a damage zone.

**Per-category resilience.** Facilities (health + education), roads and buildings are queried separately, in that priority order,
with their own cell size (`OVERPASS_FACILITY_CELL_KM` 16, `OVERPASS_CELL_KM` 12, `OVERPASS_BUILDING_CELL_KM` 4: few large cells, queries clipped to cell ∩ area, cells ordered by footprint-weighted area), cache key and error.
If buildings time out, roads and facilities are still reported and buildings are `coverage="unavailable"` (unknown, not zero, not
"no data"). Mirrors are tried once per cell; 429 waits `Retry-After` (bounded). `OVERPASS_TOTAL_BUDGET_S` limits the whole step, and each category has its own budget (`OVERPASS_FACILITY_BUDGET_S` 90, `OVERPASS_ROAD_BUDGET_S` 150, `OVERPASS_BUILDING_BUDGET_S` 180; unused time rolls over). A category that answered for only part of the cells is kept as a **lower bound** (`coverage: partial`, `coverage_pct`; the UI shows "≥ N"); one that answered for none is `unavailable` (null, never 0).

## 5. WorldPop (API V3)
Synchronous: `POST {WORLDPOP_BASE_URL}/v3/population` with `{"geojson": <Feature>, "year": N}`; the answer carries
`total_population`, `area_km2`, `population_density`, `data_year`, `data_source`, `processing_time_ms`. No task polling.
The optional key is sent as `X-API-Key` from the backend only. The year is `WORLDPOP_YEAR` (default 2020), not the event date.

Geometry sent to WorldPop is the real footprint (never a bounding box), prepared as follows and always reported
(`vertices_before/after`, `parts`, `simplification_applied`, `area_change_pct`, `chunks`, `requests`):
1. `make_valid` + dissolve (union) so overlapping parts are never counted twice;
2. drop empty parts and slivers smaller than `WORLDPOP_MIN_PART_AREA_M2` (reported);
3. simplify (topology-preserving) **only** if the total exceeds `WORLDPOP_MAX_VERTICES`;
4. split into spatially ordered groups of disjoint parts (`WORLDPOP_CHUNK_VERTICES`, `WORLDPOP_CHUNK_PARTS`, at most
   `WORLDPOP_MAX_CHUNKS`) and sum the answers. Disjoint groups cannot double count.

Errors: HTTP 413 halves the group and retries (a single part is simplified once more); 429 / 5xx / timeout get one bounded
retry and, if the service stays down, the remaining groups are not attempted. If some groups fail but the answered ones cover
at least `WORLDPOP_MIN_PARTIAL_COVERAGE_PCT` % of the area, the result is `partial`: the number is a **lower bound** and says so.
Below that coverage the population is unavailable (`null`, never 0) and the other sources are still returned.
**Caveat:** the V3 limits (maximum payload size, rate limit) and the `X-API-Key` header name are not verified from this
workspace. Run `python scripts/smoke_worldpop_v3.py` once to confirm the contract and tune the `WORLDPOP_*` values.

## 6. Sensitivity
Metrics are recomputed at thresholds 0.35/0.50/0.60/0.72/0.85 (when `include_sensitivity`), so the effect of the
threshold choice is visible.

## 7. Limits of interpretation
Satellite-derived burn areas have omission/commission error; OSM is incomplete and heterogeneous; WorldPop is a modelled
gridded surface (year-specific, not a census). None of these confirm damage, casualties or displacement.
