# Land AI Multi-Hazard Intelligence

Earth Observation + GeoAI platform for **preliminary** assessment of potentially affected areas and their exposure
(buildings, roads, health and education facilities, population). Version **3.0.0** — a new project built on top of
*Land AI Wildfire Intelligence v2*; the original project is **not modified**.

| Module | Status | Product | Method | Validation |
|---|---|---|---|---|
| **Wildfire** | Operational | Potentially fire-affected area (20 m) | FIRE FOREST COLOMBIA **V7.6** — unchanged (Sentinel-2 + VIIRS + Random Forest) | Operational, preliminary |
| **Flood** | Experimental | Detected inundation extent (10 m) | Sentinel-1 VV/VH change detection, ported from the supplied GEE script ([docs/flood/flood_gee_reference.js](docs/flood/flood_gee_reference.js)) | **Under validation** — no accuracy metrics yet |

> Results are automated, preliminary Earth Observation estimates. They are not officially validated perimeters, water depths
> or damage assessments. Intersecting buildings, roads or population with a detected area does **not** confirm damage,
> casualties or displacement.

## What is new in v3

* Hazard selector and landing state (Spanish default, English switch). Choosing or switching a hazard **never** runs an analysis.
* A common engine interface (`HazardEngine`) and a common output contract (`HazardResult`) behind `GET /api/v1/hazards` and
  `POST /api/v1/analysis/{preflight,run}`. The legacy `/api/v1/wildfire/*` routes are unchanged.
* **Flood** module with the same shared exposure engine (OSM + WorldPop) used by wildfire.
* **V1 scope is Wildfire + Flood only.** No other hazard is exposed in the UI, API or translations.
* **WorldPop V3** client (synchronous, `POST /v3/population`) that survives HTTP 413: dissolve → drop slivers → simplify only if needed → chunk.
* **Overpass per category** (facilities → roads → buildings): one failing category no longer discards the others.
* Exposure status `success | partial | failed`; unavailable metrics are `null` / “unavailable”, never zero.
* The study area (municipality or drawn polygon) is kept when you switch hazard.
* Exports (GeoJSON / CSV / JSON report) carry the hazard, product type, validation status and limitations.
* Cost controls kept: scale-to-zero Cloud Run (min instances 0, max 1 recommended), per-IP rate limits, concurrency gates,
  bounded TTL caches, kill switches (`ANALYSIS_ENABLED`, `EXPOSURE_ENABLED`), no database, no automatic computation.

## Architecture

```
Browser (React + Vite + Leaflet, GitHub Pages)
   │  landing / hazard selector / shared study-area hook / ES-EN
   ▼
FastAPI (Cloud Run)
   ├─ /api/v1/hazards, /analysis/{preflight,run}, /analysis/{id}      ← common contract (HazardResult)
   ├─ /api/v1/wildfire/*                                              ← legacy routes, unchanged
   ├─ /api/v1/exposure/{analyze,run}                                  ← shared exposure engine
   └─ hazards/  registry → WildfireEngine │ FloodEngine
                                │              │
                       V7.6 (unchanged)   Sentinel-1 reference port
                                └──────┬───────┘
                          Earth Engine (tiles, stats, footprint raster)
                                       │
                    footprint → OSM (Overpass) + WorldPop → exposure dashboard + exports
```

More detail: [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md),
[docs/flood/methodology.md](docs/flood/methodology.md), [docs/exposure-methodology.md](docs/exposure-methodology.md).

## Requirements

Python 3.11+, Node.js 18+ (22 recommended), a Google Cloud project registered for Earth Engine with read access to
`users/maikolzaraza07/mpios` (the municipalities asset), and `gcloud` for deployment.

## Run locally

```bash
cp .env.example .env                 # set EE_PROJECT (and credentials, see below)
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
cd backend && uvicorn app.main:app --reload --port 8001   # API docs: http://localhost:8001/docs

cd frontend
cp .env.example .env.local           # VITE_API_BASE_URL=http://localhost:8001
npm ci && npm run dev -- --port 5174  # http://localhost:5174
```

Ports 8001 / 5174 let it run **beside** the original app (8000 / 5173). Add `http://localhost:5174` to `CORS_ORIGINS`.
The full step-by-step guide, in Spanish, with the pre-production checklist: [docs/LOCAL_TESTING_ES.md](docs/LOCAL_TESTING_ES.md).

**Earth Engine credentials** — choose one: `earthengine authenticate` (local development; leave `EE_SERVICE_ACCOUNT` and
`EE_PRIVATE_KEY_PATH` empty) or a service-account key (`EE_PRIVATE_KEY_PATH`; the account must be registered for Earth Engine
and have read access to the municipalities asset). Never commit `.env` or key files (both are git-ignored).

## Tests

```bash
pytest -q                                                   # backend, offline (Earth Engine is not needed)
cd frontend && npm test && npm run typecheck && npm run build
```

Real-service checks (run by hand, once): `python scripts/smoke_worldpop_v3.py`, `smoke_overpass.py`, `smoke_exposure.py`, and with a running backend `smoke_wildfire.py` / `smoke_flood.py`.

Offline tests build the Earth Engine graphs without credentials and assert their structure (constants, bands, masks). They
**do not replace** a numeric comparison against the Code Editor; see the checklist in the testing guide.

## Environment variables

See [`.env.example`](.env.example) (backend) and [`frontend/.env.example`](frontend/.env.example). New in v3: `WORLDPOP_*` (V3 client, chunking, partial coverage), `OVERPASS_FACILITY_CELL_KM`, `OVERPASS_BUILDING_CELL_KM`, `OVERPASS_TOTAL_BUDGET_S`, `FLOOD_MIN_DATE`,
`FLOOD_MAX_WINDOW_DAYS`, `FLOOD_EXPOSURE_MAX_PIXELS`, `FLOOD_TILE_SCALE`, `ANALYSIS_RESULT_ITEMS`, `ANALYSIS_RESULT_TTL_SECONDS`.
Everything else is inherited unchanged from the wildfire project.

## Deployment

Nothing is deployed automatically. See [docs/deployment.md](docs/deployment.md): Cloud Run service
`landai-multihazard-api` (separate from the production wildfire service) and GitHub Pages at `/landai-multihazard/`.

## Scientific limitations (read before using results)

* **Flood is under validation.** No accuracy metrics against reference flood maps. DESCENDING passes only, no permanent-water
  mask, no slope mask (the reference script keeps it disabled), SAR confusions on smooth surfaces. See
  [docs/flood/methodology.md](docs/flood/methodology.md).
* **dB ratio finding.** The active code of the reference script divides dB values, which inverts the sign (flooded pixels become
  positive and land is flagged). The default is therefore `ratio_domain='linear'` (dB → linear power → log10); the dB variant stays
  selectable under *Advanced options* for comparison only.
* Wildfire keeps the limitations of V7.6 (see [docs/WILDFIRE_README_v2.md](docs/WILDFIRE_README_v2.md)): runtime equivalence
  with the JavaScript script is not demonstrated; likelihood is a relative score, not a calibrated probability.
* Nothing in this repository has been run against live Earth Engine from the development sandbox (no credentials there).
  The first live run is part of the local test guide.
* Costs: there is no hard spending cap in Google Cloud. Set a Billing budget alert and keep `--max-instances 1`.
* Rate limits and caches are per Cloud Run instance and in memory; they reset on restart.

## Repository layout

```
backend/app/   api/ core/ schemas/ services/ hazards/{wildfire,flood}/ wildfire/ (V7.6, unchanged)
frontend/src/  App.tsx pages/ components/ hooks/ hazards/ services/ i18n/ (v3 texts in translations.v3.ts)
docs/          architecture, api, deployment, LOCAL_TESTING_ES, flood/, exposure-methodology, wildfire notes
wildfire_gee_reference.js   V7.6 reference (unchanged)      docs/flood/flood_gee_reference.js   flood reference (verbatim)
```
