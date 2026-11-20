"""Flood map layers (Earth Engine getMapId). Same mechanism as the wildfire layers: pixels never go through FastAPI.

Groups follow the platform layer panel: ``context`` (input / reference imagery), ``results`` (the detection) and
``advanced`` (technical layers, collapsed by default in the UI).
"""
from __future__ import annotations

from ...schemas.wildfire import LegendInfo
from .optical import TRUE_COLOR_VIS

FLOOD_COLOR = '1E90FF'
RAW_COLOR = '00BFFF'
S1_VIS = {'min': -25, 'max': 0, 'bands': ['VH', 'VV', 'VH']}          # ``visRadar`` in the script
LR_VIS = {'min': -0.5, 'max': 0.5}                                     # log-ratio layers in the script
GRAY = ['#000000', '#FFFFFF']


def _solid(color: str) -> dict:
    return {'min': 0, 'max': 1, 'palette': [color]}


# (id, label, group, description, result key, vis params, visible by default, legend)
LAYER_SPECS = [
    ('s2_post', 'Sentinel-2 POST (context)', 'context',
     'True-colour composite after the event (optical context only; not used for detection).',
     's2_post', TRUE_COLOR_VIS, False, LegendInfo(type='rgb')),
    ('s2_pre', 'Sentinel-2 PRE (context)', 'context',
     'True-colour composite before the event (optical context only; not used for detection).',
     's2_pre', TRUE_COLOR_VIS, False, LegendInfo(type='rgb')),
    ('flood_extent', 'Detected inundation extent', 'results',
     'Cleaned Sentinel-1 flood mask (Otsu threshold + connected-pixel filter). Detection, not water depth.',
     'final', _solid(FLOOD_COLOR), True, LegendInfo(type='solid', colors=['#' + FLOOD_COLOR])),
    ('flood_raw', 'Flood mask before cleaning', 'advanced',
     'Threshold mask before removing small patches.', 'raw', _solid(RAW_COLOR), False,
     LegendInfo(type='solid', colors=['#' + RAW_COLOR])),
    ('log_ratio_combined', 'Log-ratio combined (min VV, VH)', 'advanced',
     'Minimum of the VV and VH log-ratios: the quantity that is thresholded.', 'lrCombined', LR_VIS, False,
     LegendInfo(type='gradient', min=-0.5, max=0.5, colors=GRAY)),
    ('log_ratio_vv', 'Log-ratio VV', 'advanced', 'Temporal change of the VV backscatter.', 'lrVV', LR_VIS, False,
     LegendInfo(type='gradient', min=-0.5, max=0.5, colors=GRAY)),
    ('log_ratio_vh', 'Log-ratio VH', 'advanced', 'Temporal change of the VH backscatter.', 'lrVH', LR_VIS, False,
     LegendInfo(type='gradient', min=-0.5, max=0.5, colors=GRAY)),
    ('s1_post', 'Sentinel-1 POST (VH, VV, VH)', 'context', 'Radar composite after the event (dB).', 'post', S1_VIS, False,
     LegendInfo(type='gradient', min=-25, max=0, colors=GRAY)),
    ('s1_pre', 'Sentinel-1 PRE (VH, VV, VH)', 'context', 'Radar composite before the event (dB).', 'pre', S1_VIS, False,
     LegendInfo(type='gradient', min=-25, max=0, colors=GRAY)),
]
