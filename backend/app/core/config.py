"""Application settings (environment variables / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', str(BACKEND_DIR / '.env'), str(REPO_ROOT / '.env')),
        extra='ignore',
    )

    ee_project: str = Field('', validation_alias=AliasChoices('EE_PROJECT', 'EE_PROJECT_ID'))
    ee_service_account: str = Field('', validation_alias='EE_SERVICE_ACCOUNT')
    ee_private_key_path: str = Field('', validation_alias='EE_PRIVATE_KEY_PATH')
    cors_origins: str = Field('http://localhost:5173,http://127.0.0.1:5173',
                              validation_alias='CORS_ORIGINS')
    municipalities_asset: str = Field('users/maikolzaraza07/mpios',
                                      validation_alias='MUNICIPALITIES_ASSET')

    # Application-layer guards (NOT part of V7.6 science)
    max_aoi_hectares: float = Field(500_000, validation_alias='MAX_AOI_HECTARES')
    warn_aoi_hectares: float = Field(100_000, validation_alias='WARN_AOI_HECTARES')
    min_fire_date: str = Field('2018-08-01', validation_alias='MIN_FIRE_DATE')

    # --- Custom AOI (drawn polygons) -------------------------------------------------
    # Municipality mode keeps MAX_AOI_HECTARES / WARN_AOI_HECTARES (unchanged behavior).
    max_custom_aoi_hectares: float = Field(100_000, validation_alias='MAX_CUSTOM_AOI_HECTARES')
    warn_custom_aoi_hectares: float = Field(50_000, validation_alias='WARN_CUSTOM_AOI_HECTARES')
    min_custom_aoi_hectares: float = Field(10, validation_alias='MIN_CUSTOM_AOI_HECTARES')
    max_polygon_vertices: int = Field(300, validation_alias='MAX_POLYGON_VERTICES')
    # Flood works on Sentinel-1 statistics only (no exposure raster), so a drawn study area may be larger than for wildfire.
    # The shipped example (the area of the reference script) is ~417,000 ha.
    flood_max_custom_aoi_hectares: float = Field(500_000, validation_alias='FLOOD_MAX_CUSTOM_AOI_HECTARES')
    flood_warn_custom_aoi_hectares: float = Field(100_000, validation_alias='FLOOD_WARN_CUSTOM_AOI_HECTARES')

    # --- Rate limiting (SlowAPI, in memory) -------------------------------------------
    rate_limit_enabled: bool = Field(True, validation_alias='RATE_LIMIT_ENABLED')
    rate_limit_analyze: str = Field('5/hour;20/day', validation_alias='RATE_LIMIT_ANALYZE')
    rate_limit_exposure: str = Field('10/hour;40/day', validation_alias='RATE_LIMIT_EXPOSURE')
    trust_forwarded_for: bool = Field(False, validation_alias='TRUST_FORWARDED_FOR')
    trusted_proxy_hops: int = Field(1, validation_alias='TRUSTED_PROXY_HOPS')

    # --- Exposure & Impact module ------------------------------------------------------
    # Independent from the wildfire AOI limits: Overpass/WorldPop/footprint cost grows with area.
    max_exposure_aoi_hectares: float = Field(40_000, validation_alias='MAX_EXPOSURE_AOI_HECTARES')
    exposure_max_pixels: int = Field(3_000_000, validation_alias='EXPOSURE_MAX_PIXELS')
    exposure_default_buffer_m: float = Field(500, validation_alias='EXPOSURE_DEFAULT_BUFFER_M')
    exposure_max_buffer_m: float = Field(2000, validation_alias='EXPOSURE_MAX_BUFFER_M')
    exposure_download_timeout_s: float = Field(600, validation_alias='EXPOSURE_DOWNLOAD_TIMEOUT_S')
    # Earth Engine evaluates a download in memory: big areas are fetched as several tiles of at most this many
    # pixels per side (+ a 104 px margin), a few in parallel. Lower it if EE reports 'User memory limit exceeded'.
    exposure_tile_px: int = Field(640, validation_alias='EXPOSURE_TILE_PX')
    exposure_tile_workers: int = Field(3, validation_alias='EXPOSURE_TILE_WORKERS')
    # Time budget for the whole footprint download; no new tile is started after it (the client waits 20 min).
    exposure_max_seconds: int = Field(1000, validation_alias='EXPOSURE_MAX_SECONDS')
    exposure_max_concurrent: int = Field(1, validation_alias='EXPOSURE_MAX_CONCURRENT')
    exposure_max_layer_features: int = Field(5000, validation_alias='EXPOSURE_MAX_LAYER_FEATURES')
    exposure_max_display_vertices: int = Field(60_000, validation_alias='EXPOSURE_MAX_DISPLAY_VERTICES')
    exposure_max_hazard_vertices: int = Field(200_000, validation_alias='EXPOSURE_MAX_HAZARD_VERTICES')
    # --- Cost / resource protection (all in-process: nothing is persisted, everything is lost on a restart) ----------
    # Manual kill switches: set to false and redeploy to stop expensive work without touching the code.
    analysis_enabled: bool = Field(True, validation_alias='ANALYSIS_ENABLED')
    exposure_enabled: bool = Field(True, validation_alias='EXPOSURE_ENABLED')
    # Wildfire analyses running at once on one instance (each holds a request thread while Earth Engine works).
    analysis_max_concurrent: int = Field(2, validation_alias='ANALYSIS_MAX_CONCURRENT')
    # Bounded, ephemeral caches. Memory ~= items x payload; payloads are bounded by the layer/vertex limits below.
    footprint_cache_items: int = Field(3, validation_alias='FOOTPRINT_CACHE_ITEMS')
    footprint_cache_ttl_seconds: int = Field(1800, validation_alias='FOOTPRINT_CACHE_TTL_SECONDS')
    exposure_cache_items: int = Field(3, validation_alias='EXPOSURE_CACHE_ITEMS')
    exposure_cache_ttl_seconds: int = Field(1800, validation_alias='EXPOSURE_CACHE_TTL_SECONDS')
    cache_max_item_bytes: int = Field(25_000_000, validation_alias='CACHE_MAX_ITEM_BYTES')
    # Live processing stages (in-memory, per instance).
    progress_ttl_seconds: int = Field(3600, validation_alias='PROGRESS_TTL_SECONDS')
    rate_limit_progress: str = Field('1200/hour', validation_alias='RATE_LIMIT_PROGRESS')
    analysis_ref_ttl_seconds: int = Field(6 * 3600, validation_alias='ANALYSIS_REF_TTL_SECONDS')
    # Secret that signs backend-issued analysis references. Empty = random per process
    # (references then stop validating after a restart / scale-to-zero).
    analysis_ref_secret: str = Field('', validation_alias='ANALYSIS_REF_SECRET')

    # OpenStreetMap / Overpass
    overpass_endpoint: str = Field('https://overpass-api.de/api/interpreter',
                                   validation_alias='OVERPASS_ENDPOINT')
    # Tried once each, in order, when the main instance answers 429/5xx/timeout (public, shared servers).
    overpass_fallback_endpoints: str = Field(
        'https://overpass.kumi.systems/api/interpreter,https://overpass.private.coffee/api/interpreter',
        validation_alias='OVERPASS_FALLBACK_ENDPOINTS')
    overpass_fallback_pause_s: float = Field(2.0, validation_alias='OVERPASS_FALLBACK_PAUSE_S')
    # Big bboxes are fetched as ~this-size cells: one huge query makes public servers answer 504.
    overpass_cell_km: float = Field(12.0, validation_alias='OVERPASS_CELL_KM')                 # roads: light, few big requests
    overpass_facility_cell_km: float = Field(16.0, validation_alias='OVERPASS_FACILITY_CELL_KM')  # health/education: sparse
    overpass_building_cell_km: float = Field(4.0, validation_alias='OVERPASS_BUILDING_CELL_KM')   # heaviest category: smaller cells
    # Wall-clock budget for ALL OpenStreetMap categories of one analysis; categories not finished in time are unavailable.
    overpass_total_budget_s: float = Field(420, validation_alias='OVERPASS_TOTAL_BUDGET_S')
    # Per-category time caps (unused time rolls over to the next category) so one slow category cannot starve the rest
    overpass_facility_budget_s: float = Field(90, validation_alias='OVERPASS_FACILITY_BUDGET_S')
    overpass_road_budget_s: float = Field(150, validation_alias='OVERPASS_ROAD_BUDGET_S')
    overpass_building_budget_s: float = Field(180, validation_alias='OVERPASS_BUILDING_BUDGET_S')
    overpass_cell_pause_s: float = Field(1.0, validation_alias='OVERPASS_CELL_PAUSE_S')
    overpass_max_cells: int = Field(40, validation_alias='OVERPASS_MAX_CELLS')
    # 429 = the server has no free slot: wait (Retry-After, default this many seconds) and ask the same server again.
    overpass_rate_limit_wait_s: float = Field(10.0, validation_alias='OVERPASS_RATE_LIMIT_WAIT_S')
    overpass_rate_limit_retries: int = Field(2, validation_alias='OVERPASS_RATE_LIMIT_RETRIES')
    overpass_user_agent: str = Field(
        'LandAI-Wildfire-Intelligence/2.0 (+https://github.com/LandAIApp/landai-wildfire)',
        validation_alias='OVERPASS_USER_AGENT')
    overpass_http_timeout_s: float = Field(90, validation_alias='OVERPASS_HTTP_TIMEOUT_S')
    overpass_query_timeout_s: int = Field(60, validation_alias='OVERPASS_QUERY_TIMEOUT_S')
    overpass_max_elements: int = Field(60_000, validation_alias='OVERPASS_MAX_ELEMENTS')
    overpass_max_response_bytes: int = Field(40_000_000, validation_alias='OVERPASS_MAX_RESPONSE_BYTES')
    overpass_max_concurrent: int = Field(1, validation_alias='OVERPASS_MAX_CONCURRENT')
    overpass_cache_ttl_seconds: int = Field(6 * 3600, validation_alias='OVERPASS_CACHE_TTL_SECONDS')

    # WorldPop (the optional key lives ONLY here, never in the frontend)
    worldpop_base_url: str = Field('https://api.worldpop.org', validation_alias='WORLDPOP_BASE_URL')
    worldpop_api_version: str = Field('v3', validation_alias='WORLDPOP_API_VERSION')   # v3 only (v2 task polling removed)
    worldpop_year: int = Field(2020, validation_alias='WORLDPOP_YEAR')
    worldpop_resolution: str = Field('100m', validation_alias='WORLDPOP_RESOLUTION')  # metadata: V3 serves the 100 m grid
    worldpop_api_key: str = Field('', validation_alias='WORLDPOP_API_KEY')
    worldpop_http_timeout_s: float = Field(60, validation_alias='WORLDPOP_HTTP_TIMEOUT_S')
    worldpop_retry_wait_s: float = Field(3, validation_alias='WORLDPOP_RETRY_WAIT_S')   # one bounded retry on 429/5xx/timeout
    # Geometry preparation (see services/worldpop.py): dissolve -> drop slivers -> simplify only if needed -> chunk.
    worldpop_max_vertices: int = Field(20_000, validation_alias='WORLDPOP_MAX_VERTICES')            # total, before chunking
    worldpop_simplify_tolerance_m: float = Field(5, validation_alias='WORLDPOP_SIMPLIFY_TOLERANCE_M')
    worldpop_min_part_area_m2: float = Field(50, validation_alias='WORLDPOP_MIN_PART_AREA_M2')    # slivers only
    worldpop_chunk_vertices: int = Field(3_000, validation_alias='WORLDPOP_CHUNK_VERTICES')        # per request
    worldpop_chunk_parts: int = Field(100, validation_alias='WORLDPOP_CHUNK_PARTS')                # per request
    worldpop_max_chunks: int = Field(30, validation_alias='WORLDPOP_MAX_CHUNKS')
    worldpop_min_partial_coverage_pct: float = Field(80, validation_alias='WORLDPOP_MIN_PARTIAL_COVERAGE_PCT')
    worldpop_cache_ttl_seconds: int = Field(24 * 3600, validation_alias='WORLDPOP_CACHE_TTL_SECONDS')

    # --- Flood module (Sentinel-1 reference method, see hazards/flood) -------------------------------------------------
    flood_min_date: str = Field('2015-01-01', validation_alias='FLOOD_MIN_DATE')
    # Longest PRE or POST window accepted (application guard, not part of the reference script).
    flood_max_window_days: int = Field(90, validation_alias='FLOOD_MAX_WINDOW_DAYS')
    # The flood footprint is rasterised at its native 10 m (the reference script's scale), so the same pixel budget covers
    # a quarter of the ground area of the 20 m wildfire raster. 6 M pixels = 600 km2.
    flood_exposure_max_pixels: int = Field(6_000_000, validation_alias='FLOOD_EXPOSURE_MAX_PIXELS')
    # Earth Engine memory/latency only (never changes a value): reduceRegion tileScale for the Otsu histogram and areas.
    flood_tile_scale: int = Field(4, validation_alias='FLOOD_TILE_SCALE')

    # --- Common analysis registry (GET /api/v1/analysis/{id}); ephemeral, bounded, per instance ----------------------------
    analysis_result_items: int = Field(20, validation_alias='ANALYSIS_RESULT_ITEMS')
    analysis_result_ttl_seconds: int = Field(1800, validation_alias='ANALYSIS_RESULT_TTL_SECONDS')

    log_level: str = Field('INFO', validation_alias='LOG_LEVEL')

    @model_validator(mode='after')
    def _check_limits(self) -> 'Settings':
        if self.warn_custom_aoi_hectares > self.max_custom_aoi_hectares:
            self.warn_custom_aoi_hectares = self.max_custom_aoi_hectares
        if self.flood_warn_custom_aoi_hectares > self.flood_max_custom_aoi_hectares:
            self.flood_warn_custom_aoi_hectares = self.flood_max_custom_aoi_hectares
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(',') if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
