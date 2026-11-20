import type { HazardId, HazardInfo } from '../types/api';

export const HAZARD_ORDER: readonly HazardId[] = ['wildfire', 'flood'];

/**
 * What the UI assumes until GET /api/v1/hazards answers (or when the backend is an older, wildfire-only release).
 * The backend answer is authoritative: this fallback never claims more than what the modules really are.
 */
export const FALLBACK_HAZARDS: HazardInfo[] = [
  {
    id: 'wildfire', module_status: 'operational', analysis_available: true, exposure_available: true,
    product_types: ['observed_footprint'], product_label: { en: 'Potentially fire-affected area', es: 'Área potencialmente afectada por incendio' },
    validation_status: 'operational_preliminary', methodology: null, resolution_m: 20,
    disclaimer: { en: '', es: '' },
  },
  {
    id: 'flood', module_status: 'experimental', analysis_available: true, exposure_available: true,
    product_types: ['potential_detection'], product_label: { en: 'Detected inundation extent', es: 'Extensión de inundación detectada' },
    validation_status: 'under_validation', methodology: null, resolution_m: 10,
    disclaimer: { en: '', es: '' },
  },
];

/** Merge the backend answer over the fallback, keeping the fixed order and never dropping a module. */
export function mergeHazards(remote: HazardInfo[] | null | undefined): HazardInfo[] {
  const byId = new Map((remote ?? []).map((h) => [h.id, h]));
  return HAZARD_ORDER.map((id) => byId.get(id) ?? FALLBACK_HAZARDS.find((h) => h.id === id)!);
}
