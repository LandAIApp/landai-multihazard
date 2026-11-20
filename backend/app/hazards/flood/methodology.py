"""Flood methodology content (EN/ES) shown by the common methodology panel, plus the module's static metadata."""
from __future__ import annotations

from ...schemas.common import DataSource, LocalizedText, Methodology, Notice

METHOD_NAME = 'Sentinel-1 SAR VV/VH change detection (log-ratio + Otsu)'
METHOD_VERSION = 'reference-script-1'
REFERENCE = 'docs/flood/flood_gee_reference.js · docs/flood/methodology.md'

DATA_SOURCES = [
    DataSource(name='Sentinel-1 GRD (COPERNICUS/S1_GRD)', role='detection',
               detail='IW mode, VV+VH, DESCENDING orbit pass, median composite per window, focal median 30 m'),
    DataSource(name='Sentinel-2 SR Harmonized + Cloud Probability', role='visual context only',
               detail='true-colour composites for PRE and POST (not used to detect water)'),
]

LIMITATIONS = [
    Notice(code='flood_method_under_validation',
           message='The method follows the reference script. No accuracy metrics (against reference flood maps) have been '
                   'computed yet, so the result is under validation.'),
    Notice(code='flood_extent_only',
           message='The product is a detected inundation extent. It is not a water depth, a hydraulic simulation, a '
                   'flood probability or a damage assessment.'),
    Notice(code='flood_descending_only',
           message='Only DESCENDING passes are used: the PRE and POST composites come from one acquisition geometry.'),
    Notice(code='flood_no_permanent_water_mask',
           message='There is no permanent-water mask: rivers, reservoirs and ponds that were already water in the PRE '
                   'period can produce no change, but wet-soil, vegetation and wind effects can still produce false '
                   'detections.'),
    Notice(code='flood_no_slope_mask',
           message='The slope mask defined in the reference script is not applied (the script keeps it disabled), so steep '
                   'terrain and radar shadow can generate false detections.'),
    Notice(code='flood_sar_confusions',
           message='Radar backscatter drops over smooth surfaces (wet sand, paved areas, shadow); flooded vegetation and '
                   'urban areas can be under-detected.'),
    Notice(code='flood_otsu_dependency',
           message='The Otsu threshold is computed on the whole study area: results depend on the area and on the share '
                   'of the area that actually changed.'),
]

RATIO_NOTE = Notice(
    code='flood_ratio_domain',
    message='Backscatter change is computed as log10(post/pre) on linear power (dB converted first), so a drop in '
            'backscatter (open water) is negative and is selected by the threshold.')

PENDING_NOTE = LocalizedText(en='', es='')

METHODOLOGY = Methodology(name=METHOD_NAME, version=METHOD_VERSION, reference=REFERENCE)
