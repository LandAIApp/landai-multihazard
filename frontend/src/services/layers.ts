import { translateOptional, type Language } from '../i18n';
import type { LayerInfo } from '../types/api';

/** Layers shown by default in the "Main" group. Every other layer is "Advanced". */
export const MAIN_LAYER_IDS: readonly string[] = ['post', 'burn_050', 'burn_072', 'viirs'];

export const FLOOD_MAIN_LAYER_IDS: readonly string[] = ['flood_extent', 's1_post', 's1_pre', 's2_post', 's2_pre'];

export function splitLayers(layers: LayerInfo[], mainIds: readonly string[] = MAIN_LAYER_IDS): { main: LayerInfo[]; advanced: LayerInfo[] } {
  return {
    main: layers.filter((l) => mainIds.includes(l.id)),
    advanced: layers.filter((l) => !mainIds.includes(l.id)),
  };
}

/** Localized name; falls back to the server label for unknown layer ids. */
export function layerLabel(lang: Language, layer: LayerInfo): string {
  return translateOptional(lang, `layers.${layer.id}.label`) ?? layer.label;
}

export function layerDescription(lang: Language, layer: LayerInfo): string {
  return translateOptional(lang, `layers.${layer.id}.desc`) ?? layer.description;
}
