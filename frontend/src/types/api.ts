export interface Issue { code: string; message: string; params?: Record<string, number | string> }
export type LngLat = [number, number];
export type Ring = LngLat[];
export interface PolygonGeometry { type: 'Polygon'; coordinates: Ring[] }
export interface DateRange { start: string | null; end: string | null }
export interface DateWindows { pre: DateRange; post: DateRange; history: DateRange }

/** Select the study area EITHER by municipality (original contract) OR by a drawn polygon. */
export interface WildfireRequest {
  department?: string;
  municipality?: string;
  geometry?: PolygonGeometry;
  fire_date: string;
  analysis_end: string;
  /** Random id so the UI can poll the real processing stages. */
  progress_id?: string;
}

export interface PreflightResponse {
  status: 'ok' | 'blocked';
  valid: boolean;
  pre_count: number | null;
  post_count: number | null;
  history_count: number | null;
  date_windows: DateWindows | null;
  aoi_hectares: number | null;
  aoi_kind?: 'municipality' | 'drawn' | null;
  warnings: Issue[];
  blocking_errors: Issue[];
}

export interface AreaEntry { threshold: number; key: string; label: string; hectares: number }

export interface Legend {
  type: 'gradient' | 'solid' | 'rgb';
  min: number | null;
  max: number | null;
  colors: string[];
}

export interface LayerInfo {
  id: string;
  label: string;
  group: string;
  description: string;
  tile_url: string;
  visible_by_default: boolean;
  legend: Legend | null;
}

export interface AnalyzeResponse {
  status: 'ok';
  metadata: {
    model_version: string;
    equivalence_validated: boolean;
    aoi_kind?: 'municipality' | 'drawn';
    department: string | null;
    municipality: string | null;
    fire_date: string;
    analysis_end: string;
    aoi_hectares: number | null;
    generated_at: string;
    disclaimer: string;
  };
  image_counts: { pre: number; post: number; history: number };
  date_windows: DateWindows;
  training: { positive_samples: number; negative_samples: number; note: string };
  area_statistics: Record<string, number>;
  area_hectares: AreaEntry[];
  layers: LayerInfo[];
  boundary: GeoJSON.Feature;
  bounds: [[number, number], [number, number]];
  warnings: Issue[];
  /** v2: signed reference the Exposure module uses (never a client-supplied polygon). */
  analysis_ref?: string | null;
  aoi?: { kind: 'municipality' | 'drawn'; hectares: number | null; department: string | null; municipality: string | null } | null;
}

export interface ApiErrorBody {
  status: 'error';
  code: string;
  message: string;
  details?: unknown;
}

/** GET /api/v1/config: the authoritative limits (never hard-coded in the UI). */
export interface PublicConfig {
  status: string;
  /** Per-hazard limits (flood date guards, native resolution). */
  hazards?: { flood?: { min_date: string; max_window_days: number; exposure_max_pixels: number; resolution_m: number; max_custom_hectares?: number; warn_custom_hectares?: number } };
  version: string;
  aoi: {
    municipality: { max_hectares: number; warn_hectares: number };
    custom: { max_hectares: number; warn_hectares: number; min_hectares: number; max_vertices: number };
    min_fire_date: string;
  };
  exposure: {
    max_aoi_hectares: number; default_buffer_m: number; max_buffer_m: number; max_layer_features: number;
    thresholds: number[]; default_threshold: number; population_year: number; population_resolution: string;
  };
  rate_limits: { analyze: { count: number; per: string }[]; exposure: { count: number; per: string }[]; enabled: boolean };
  sources: Record<string, string>;
  service?: ServiceInfo;
}

export interface ServiceInfo {
  analysis_enabled: boolean; exposure_enabled: boolean;
  max_concurrent_exposure: number; max_concurrent_analysis: number;
  max_exposure_seconds: number; cache_ttl_seconds: number;
}

export type StageState = 'pending' | 'running' | 'done' | 'cached' | 'skipped' | 'failed';
export interface ProgressStage {
  key: string; state: StageState; seconds: number | null;
  detail: { cells_done?: number; cells_total?: number; error?: string };
}
export interface ProgressSnapshot { status: 'ok'; elapsed_s: number; finished: boolean; stages: ProgressStage[] }

// ---------------- Exposure & Impact ----------------
export interface ExposureRequest {
  analysis_ref: string;
  threshold: number;
  buffer_m?: number;
  include_population?: boolean;
  include_sensitivity?: boolean;
  progress_id?: string;
}

export type MetricCoverage = 'mapped' | 'no_osm_data' | 'unavailable' | 'partial';
export interface ExposureMetric { value: number | null; coverage: MetricCoverage; unit: string; coverage_pct?: number }

export interface PopulationMetric {
  value: number | null;
  status: 'ok' | 'partial' | 'unavailable' | 'skipped';
  unit: 'people';
  /** Partial answer (some groups of the footprint failed): the value is a lower bound. */
  chunks?: number; chunks_failed?: number; coverage_pct?: number;
  year?: number;
  resolution?: string;
  dataset?: string;
  api_version?: string;
  analysis_area_ha?: number;
  simplification?: { applied: boolean; vertices_before: number; vertices_after: number; tolerance_m: number; area_change_pct: number };
  uncertainty_note?: string;
  reason?: string;
}

export type SourceKey = 'earth_observation' | 'openstreetmap' | 'worldpop';
export interface SourceStatus {
  status: 'success' | 'partial' | 'error' | 'skipped';
  details: Record<string, unknown>;
  error?: { code: string; message: string; details?: unknown } | null;
}

export interface ExposureMetrics {
  affected_area_ha: number;
  affected_area_km2: number;
  aoi_ha: number;
  affected_pct_of_aoi: number | null;
  population: PopulationMetric;
  buildings_intersecting: ExposureMetric;
  buildings_within_buffer: ExposureMetric;
  roads_km_intersecting: ExposureMetric;
  roads_km_within_buffer: ExposureMetric;
  health_intersecting: ExposureMetric;
  health_within_buffer: ExposureMetric;
  education_intersecting: ExposureMetric;
  education_within_buffer: ExposureMetric;
}

export interface FacilityRow { osm: string; name: string | null; class: string; distance_m: number; status: string }

export interface ExposureDetails {
  buildings_by_category?: Record<string, { intersecting: number; within_buffer: number }> | null;
  buildings_footprint_m2?: number | null;
  roads_km_by_class?: Record<string, number> | null;
  health_facilities?: FacilityRow[] | null;
  education_facilities?: FacilityRow[] | null;
  osm_features_in_study_area?: Record<string, number>;
}

export interface ExposureWarning { code: string; message: string; params: Record<string, number | string> }

export interface SensitivityRow {
  threshold: number; key: string; label: string; area_ha: number;
  buildings_intersecting: number | null; roads_km_intersecting: number | null;
  health_intersecting: number | null; education_intersecting: number | null; selected: boolean;
}

export type ExposureLayerName = 'footprint' | 'aoi' | 'buffer' | 'buildings' | 'roads' | 'health' | 'education';
export interface ExposureFeatureCollection extends GeoJSON.FeatureCollection {
  metadata?: { total?: number; shown?: number; display?: Record<string, unknown> };
}

export interface ExposureResponse {
  status: 'success' | 'partial' | 'failed';
  hazard_type: 'wildfire' | 'flood';
  mode: 'wildfire_analysis' | 'flood_analysis' | 'external_polygon';
  analysis: {
    mode: string; aoi_kind: 'municipality' | 'drawn'; aoi_hectares: number;
    department: string | null; municipality: string | null;
    threshold: number | null; threshold_label: string | null;
    event_date: string | null; analysis_end: string | null;
    date_windows: DateWindows | null; model_version: string | null;
    buffer_m: number; generated_at: string;
    custom_aoi_note: string | null;
    /** Multi-hazard additions (absent in answers recorded before the multi-hazard release). */
    hazard?: 'wildfire' | 'flood';
    footprint_label?: { en: string; es: string };
    product?: {
      hazard: string; product_type: string; validation_status: string | null; resolution_m: number | null;
      methodology: { name: string; version: string } | null; limitations: { code: string; message: string }[];
    };
    /** Server-side processing info: stage timings and whether the answer came from the in-memory cache. */
    processing?: { timings_s?: Record<string, number | boolean>; served_from_cache?: boolean };
  };
  metrics: ExposureMetrics;
  details: ExposureDetails;
  sensitivity: SensitivityRow[];
  sources: Record<SourceKey, SourceStatus>;
  warnings: ExposureWarning[];
  layers: Partial<Record<ExposureLayerName, ExposureFeatureCollection>>;
  exports: { csv: string; report: Record<string, unknown> };
  notice: { en: string; es: string };
}

/** A real result recorded from live services (frontend/public/demo/exposure-demo.json). */
export interface RecordedDemo {
  recorded: true;
  recorded_at: string;
  recorded_from_live_services: true;
  event: string;
  analysis: AnalyzeResponse;
  exposure: ExposureResponse;
}


// ---------------- Multi-hazard platform ----------------
export type HazardId = 'wildfire' | 'flood';
export type ProductType = 'observed_footprint' | 'potential_detection' | 'anomaly' | 'susceptibility';
export type ValidationStatus = 'operational_preliminary' | 'experimental' | 'under_validation';
export type ModuleStatus = 'operational' | 'experimental';
export interface LocalizedText { en: string; es: string }
export interface Notice { code: string; message: string; params?: Record<string, number | string> }

/** GET /api/v1/hazards: what each module really is today (drives the selector and the landing cards). */
export interface HazardInfo {
  id: HazardId;
  module_status: ModuleStatus;
  analysis_available: boolean;
  exposure_available: boolean;
  product_types: ProductType[];
  product_label: LocalizedText;
  validation_status: ValidationStatus;
  methodology: { name: string; version: string; reference?: string | null } | null;
  resolution_m: number | null;
  pending_reason?: LocalizedText | null;
  disclaimer: LocalizedText;
}

export interface FloodParams {
  pre_start: string; pre_end: string; post_start: string; post_end: string;
  ratio_domain?: 'reference' | 'linear';
}

/** Common request of POST /api/v1/analysis/preflight|run. */
export interface HazardRequest {
  hazard: HazardId;
  department?: string;
  municipality?: string;
  geometry?: PolygonGeometry;
  params: FloodParams | Record<string, unknown>;
  progress_id?: string;
}

export interface HazardPreflight {
  hazard_type: HazardId;
  status: 'ok' | 'blocked';
  valid: boolean;
  aoi_hectares: number | null;
  aoi_kind?: 'municipality' | 'drawn' | null;
  counts: Record<string, number | null>;
  date_windows: Record<string, { start: string | null; end: string | null }>;
  warnings: Notice[];
  blocking_errors: Notice[];
}

/** The common result contract (identical for every hazard). */
export interface HazardResult {
  analysis_id: string;
  hazard_type: HazardId;
  product_type: ProductType;
  product_label: LocalizedText;
  status: 'ok';
  aoi: { kind: 'municipality' | 'drawn'; hectares: number | null; department: string | null; municipality: string | null };
  analysis_period: Record<string, unknown>;
  methodology: { name: string; version: string; reference?: string | null };
  data_sources: { name: string; role: string; detail?: string | null }[];
  resolution: { spatial_m: number; note?: string | null };
  validation_status: ValidationStatus;
  statistics: Record<string, unknown>;
  layers: LayerInfo[];
  boundary: GeoJSON.Feature;
  bounds: [[number, number], [number, number]];
  footprint_reference: string | null;
  warnings: Notice[];
  limitations: Notice[];
  generated_at: string;
  exposure_ready: boolean;
  details: Record<string, unknown>;
  disclaimer?: LocalizedText | null;
}

export interface FloodStatistics {
  flood_hectares: number; flood_raw_hectares: number; flood_pct_of_aoi: number | null;
  otsu_threshold: number | null; ratio_domain: 'reference' | 'linear';
  scene_counts: { s1_pre: number; s1_post: number; s2_pre: number; s2_post: number };
}
