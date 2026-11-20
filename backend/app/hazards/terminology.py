"""Product wording and disclaimers per hazard (EN/ES). One place, so the API and the exports use the same terms.

Rules: a detection is not a confirmed inventory; exposure is not damage; susceptibility is not risk and does not say
WHEN anything happens; a flood extent is not a water depth.
"""
from __future__ import annotations

from ..schemas.common import LocalizedText

GENERAL_DISCLAIMER = LocalizedText(
    en=('Results are preliminary automated Earth Observation products intended to support technical assessment. '
        'They do not replace official field verification or authoritative hazard products.'),
    es=('Los resultados son productos preliminares automatizados de Observación de la Tierra, pensados para apoyar la '
        'evaluación técnica. No reemplazan la verificación en campo ni los productos oficiales de amenaza.'))

PRODUCT_LABEL = {
    'wildfire': LocalizedText(en='Potentially burned area', es='Área potencialmente quemada'),
    'flood': LocalizedText(en='Detected inundation extent', es='Extensión de inundación detectada'),
}

HAZARD_DISCLAIMER = {
    'wildfire': LocalizedText(
        en='A potentially burned area is not a confirmed official fire perimeter.',
        es='Un área potencialmente quemada no es un perímetro oficial confirmado del incendio.'),
    'flood': LocalizedText(
        en='A detected inundation extent is not a water depth, a hydraulic simulation or a damage assessment.',
        es='Una extensión de inundación detectada no es una profundidad de agua, una simulación hidráulica ni una '
           'evaluación de daños.'),
}

# Used by the exposure report: what the "footprint" is, per hazard.
FOOTPRINT_DEFINITION = {
    'wildfire': 'Satellite-derived potentially burned area at the selected threshold.',
    'flood': 'Satellite-derived detected inundation extent (Sentinel-1 change detection).',
}
STUDY_AREA_DEFINITION = {
    'wildfire': 'Area analysed by the wildfire model (municipality or drawn polygon).',
    'flood': 'Area analysed by the flood detection method (municipality or drawn polygon).',
}
FOOTPRINT_LABEL = {
    'wildfire': LocalizedText(en='Potentially burned area', es='Área potencialmente quemada'),
    'flood': LocalizedText(en='Detected inundation extent', es='Extensión de inundación detectada'),
}
