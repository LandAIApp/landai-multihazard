# Architecture (v3, multi-hazard)

* **Frontend** — static React/Vite/Leaflet app (GitHub Pages). `App.tsx` is the shell: landing → hazard workspace.
  `useAoi` (study area) is shared by the wildfire and flood workspaces and remembered across hazard switches
  (`AoiMemoryProvider`). `HazardTextScope` lets shared components say "detected inundation extent" for a flood and keep every
  wildfire text unchanged (`<key>.<hazard>` overrides in `translations.v3.ts`). Limits are read from `GET /api/v1/config`.
* **Backend** — FastAPI on Cloud Run (scale-to-zero, no database).
  * `hazards/base.py`: `HazardEngine` — `info`, `preflight`, `analyze`, `get_layers`, `get_statistics`, `get_metadata`.
  * `hazards/__init__.py`: `get_engine('wildfire' | 'flood')` (V1 scope: only these two hazards).
  * `hazards/wildfire`: thin adapter over the unchanged `run_analysis` / `run_preflight` (V7.6).
  * `hazards/flood`: port of the reference script (`s1.py`, `otsu.py`, `optical.py`, `tiles.py`, `footprint.py`, `engine.py`).
  * `schemas/common.py`: the common contract (`HazardResult`, `HazardInfo`, `AnalysisRequest`, `PreflightResult`).
  * `services/exposure.py`: shared exposure engine; the signed `analysis_ref` carries the hazard (tokens without it mean wildfire).
* **Earth Engine** — compute, map tiles and the footprint raster. **OSM (Overpass)** and **WorldPop** are called only from the
  backend and only after the explicit "Analyze exposure" action.
* **Flow** — choose hazard → choose area → (optional) check availability → run analysis → result + `analysis_ref` →
  (optional) *Analyze exposure* → dashboard + exports. Each arrow is an explicit user action.

Product vocabulary (`product_type`): `observed_footprint`, `potential_detection`, `anomaly`, `susceptibility`.
Validation (`validation_status`): `operational_preliminary`, `experimental`, `under_validation`.
Module status: `operational`, `experimental`.

## External sources (exposure)
* **WorldPop V3** (`services/worldpop.py`): synchronous `POST /v3/population`. The footprint is dissolved, slivers are
  dropped, it is simplified only if over `WORLDPOP_MAX_VERTICES`, then split into spatially ordered disjoint groups.
  HTTP 413 halves the group; 429/5xx/timeout get one bounded retry. A partial answer is accepted only if it covers
  >= `WORLDPOP_MIN_PARTIAL_COVERAGE_PCT` of the area and is labelled as a lower bound; otherwise population is unavailable.
* **OpenStreetMap / Overpass** (`services/osm.py`): three independent categories (facilities -> roads -> buildings), each with
  its own cell size, cache and error. One failing category does not discard the others; a wall-clock budget
  (`OVERPASS_TOTAL_BUDGET_S`) bounds the whole step.
* **Statuses**: overall `success | partial | failed`; per source `success | partial | error | skipped`; an unavailable metric is
  `value: null` with `coverage: "unavailable"` - never zero. Only `success` results are cached.
