"""Flood engine: Sentinel-1 VV/VH change detection, ported from the reference Google Earth Engine script.

Scientific status: UNDER VALIDATION. The method is exactly the one of the reference script; no accuracy metrics have been
computed. See docs/flood/methodology.md for the line-by-line mapping and the findings of the review.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ...core import progress as progress_mod
from ...core.config import get_settings
from ...core.earth_engine import evaluate
from ...core.errors import MunicipalityNotFoundError, PreflightFailedError, ServicePausedError
from ...core.gate import slot
from ...core.memo import Memo, fingerprint
from ...core.progress import NullProgress, Progress
from ...schemas.common import (
    AnalysisRequest, HazardInfo, HazardResult, LocalizedText, Methodology, Notice, PreflightResult, Resolution,
)
from ...services import analysis_ref, study_area
from ...services.tiles import build_layers
from .. import terminology as T
from ..base import HazardEngine
from . import methodology as M
from . import s1
from .params import FloodParams, date_issues, parse_params
from .tiles import LAYER_SPECS

logger = logging.getLogger('landai.flood')

ANALYSIS_STAGES = ['preflight', 'sar_processing', 'statistics', 'layers']
# Application heuristic (NOT part of the reference method): a very large detected share of the study area is more often a
# sign of a threshold/ratio problem than of a real event, so the user is told to check it.
LARGE_EXTENT_PCT = 40.0
_flights = Memo(max_items=1)


def reset_flights() -> None:
    _flights.clear()


def _model_version(params: FloodParams) -> str:
    return f'{M.METHOD_NAME} · {M.METHOD_VERSION} · ratio_domain={params.ratio_domain}'


def _flood_limits(settings):
    """Settings with the flood-specific drawn-area limits (flood needs no exposure raster, so it may be larger)."""
    return settings.model_copy(update={'max_custom_aoi_hectares': settings.flood_max_custom_aoi_hectares,
                                       'warn_custom_aoi_hectares': settings.flood_warn_custom_aoi_hectares})


class FloodEngine(HazardEngine):
    hazard_id = 'flood'

    # ---- metadata -------------------------------------------------------------------------------------------
    def info(self) -> HazardInfo:
        return HazardInfo(
            id='flood', module_status='experimental', analysis_available=True, exposure_available=True,
            product_types=['potential_detection'], product_label=T.PRODUCT_LABEL['flood'],
            validation_status='under_validation', methodology=M.METHODOLOGY, resolution_m=s1.MASK_SCALE_M,
            disclaimer=T.HAZARD_DISCLAIMER['flood'])

    def get_metadata(self) -> dict[str, Any]:
        return {'methodology': M.METHODOLOGY.model_dump(), 'data_sources': [s.model_dump() for s in M.DATA_SOURCES],
                'limitations': [n.model_dump() for n in M.LIMITATIONS] + [M.RATIO_NOTE.model_dump()],
                'disclaimer': T.HAZARD_DISCLAIMER['flood'].model_dump()}

    # ---- preflight --------------------------------------------------------------------------------------------
    def preflight(self, req: AnalysisRequest) -> PreflightResult:
        result, _area_ctx = self._preflight(req)
        return result

    def _preflight(self, req: AnalysisRequest):
        params = parse_params(req.params)
        settings = get_settings()
        blocking = date_issues(params, settings)
        windows = {'pre': {'start': params.pre_start.isoformat(), 'end': params.pre_end.isoformat()},
                   'post': {'start': params.post_start.isoformat(), 'end': params.post_end.isoformat()}}

        def blocked(hectares=None, warnings=None) -> PreflightResult:
            return PreflightResult(hazard_type='flood', status='blocked', valid=False, aoi_hectares=hectares,
                                   aoi_kind=req.aoi_kind, date_windows=windows, warnings=warnings or [],
                                   blocking_errors=blocking)

        if blocking:                       # invalid dates never cost an Earth Engine call
            return blocked(), None
        hectares, area_blocking, warnings, handle = study_area.preflight_area(req, _flood_limits(settings))
        blocking += area_blocking
        if blocking:
            return blocked(hectares, warnings), None
        area = study_area.build(req, hectares, handle)           # type: ignore[arg-type]
        counts = evaluate(s1.availability(area.geometry, *windows['pre'].values(), *windows['post'].values()),
                          'checking Sentinel-1 availability')
        s1_pre, s1_post = int(counts['s1_pre']), int(counts['s1_post'])
        s2_pre, s2_post = int(counts['s2_pre']), int(counts['s2_post'])
        if s1_pre < 1:
            blocking.append(Notice(code='no_s1_pre_images',
                                   message='No Sentinel-1 images (IW, VV+VH, descending) exist for the PRE window.'))
        if s1_post < 1:
            blocking.append(Notice(code='no_s1_post_images',
                                   message='No Sentinel-1 images (IW, VV+VH, descending) exist for the POST window.'))
        if not blocking:
            if s1_pre < 2 or s1_post < 2:
                warnings.append(Notice(code='few_s1_scenes',
                                       message='Very few Sentinel-1 scenes are available; the composite is less robust.',
                                       params={'s1_pre': s1_pre, 's1_post': s1_post}))
            if s2_pre < 1 or s2_post < 1:
                warnings.append(Notice(code='no_s2_context',
                                       message='There are no clear Sentinel-2 images for one of the windows: the optical '
                                               'context layers will not be available (the detection does not need them).'))
        result = PreflightResult(
            hazard_type='flood', status='blocked' if blocking else 'ok', valid=not blocking, aoi_hectares=hectares,
            aoi_kind=area.kind, counts={'s1_pre': s1_pre, 's1_post': s1_post, 's2_pre': s2_pre, 's2_post': s2_post},
            date_windows=windows, warnings=warnings, blocking_errors=blocking)
        return result, area

    # ---- analysis ---------------------------------------------------------------------------------------------
    def analyze(self, req: AnalysisRequest) -> HazardResult:
        settings = get_settings()
        if not settings.analysis_enabled:
            raise ServicePausedError('The analysis is temporarily paused by the operator.')
        params = parse_params(req.params)
        progress = progress_mod.begin(req.progress_id, ANALYSIS_STAGES)
        key = fingerprint('flood-analysis', _model_version(params),
                          req.model_dump(mode='json', exclude={'progress_id'}))

        def compute() -> HazardResult:
            with slot('analysis', settings.analysis_max_concurrent,
                      busy_message='The server is running other analyses. Please retry in a minute.'):
                return self._run(req, params, progress)

        try:
            result, how = _flights.get_or_compute(key, compute, ttl=0)
            if how != 'computed':
                logger.info('flood_analysis_shared with an identical request already running')
            return result
        finally:
            progress.close()

    def _run(self, req: AnalysisRequest, params: FloodParams, progress: Progress | None = None) -> HazardResult:
        progress = progress or NullProgress()
        settings = get_settings()
        started = time.perf_counter()
        logger.info('analysis_started hazard=flood aoi=%s department=%s municipality=%s pre=%s..%s post=%s..%s ratio=%s',
                    req.aoi_kind, req.department or '(drawn)', req.municipality or '(drawn)', params.pre_start,
                    params.pre_end, params.post_start, params.post_end, params.ratio_domain)
        progress.start('preflight')
        pre, area = self._preflight(req)
        progress.finish('preflight')
        logger.info('preflight_completed hazard=flood valid=%s seconds=%.1f', pre.valid, time.perf_counter() - started)
        if not pre.valid or area is None:
            if any(e.code == 'municipality_not_found' for e in pre.blocking_errors):
                raise MunicipalityNotFoundError(pre.blocking_errors[0].message)
            raise PreflightFailedError(
                'The analysis cannot run: ' + ' '.join(e.message for e in pre.blocking_errors),
                details=[e.model_dump() for e in pre.blocking_errors])

        progress.start('sar_processing')
        graph = s1.flood_graph(area.geometry, params.pre_start.isoformat(), params.pre_end.isoformat(),
                               params.post_start.isoformat(), params.post_end.isoformat(), params.ratio_domain,
                               settings.flood_tile_scale)
        progress.finish('sar_processing')

        progress.start('statistics')
        raw = evaluate(s1.statistics(graph, area.geometry, settings.flood_tile_scale),
                       'calculating the detected inundation extent') or {}
        progress.finish('statistics')
        hectares = float(raw.get('floodHectares') or 0.0)
        raw_hectares = float(raw.get('floodRawHectares') or 0.0)
        threshold = raw.get('otsuThreshold')
        pct = round(hectares / area.hectares * 100, 2) if area.hectares else None
        logger.info('hazard_processing_completed hazard=flood flood_ha=%.2f otsu=%s seconds=%.1f',
                    hectares, threshold, time.perf_counter() - started)

        warnings = list(pre.warnings)
        if hectares <= 0:
            warnings.append(Notice(code='no_flood_detected',
                                   message='No inundated area was detected with this method for these windows.'))
        if pct is not None and pct > LARGE_EXTENT_PCT:
            warnings.append(Notice(code='flood_extent_very_large',
                                   message=f'The detected extent covers {pct:.0f}% of the study area. Check the '
                                           'log-ratio layers and the ratio_domain setting before using this result.',
                                   params={'pct': pct, 'limit_pct': LARGE_EXTENT_PCT}))

        progress.start('layers')
        layers, layer_warnings = self._layers(graph, area.geometry, params, pre)
        progress.finish('layers')
        warnings += [Notice(code=w.code, message=w.message, params=dict(w.params)) for w in layer_warnings]
        logger.info('layers_generated hazard=flood layers=%s', len(layers))

        analysis_id = uuid.uuid4().hex
        token_payload = {
            'hazard': 'flood', 'kind': area.kind, 'aoi_hectares': area.hectares,
            'model_version': _model_version(params), 'area_ha': {'flood': hectares},
            'params': {'pre_start': params.pre_start.isoformat(), 'pre_end': params.pre_end.isoformat(),
                       'post_start': params.post_start.isoformat(), 'post_end': params.post_end.isoformat(),
                       'ratio_domain': params.ratio_domain},
        }
        if area.kind == 'drawn':
            token_payload['ring'] = area.ring
        else:
            token_payload['department'], token_payload['municipality'] = area.department, area.municipality
        reference = analysis_ref.issue(token_payload)

        logger.info('analysis_completed hazard=flood aoi_ha=%.1f duration_seconds=%.1f success=true',
                    area.hectares, time.perf_counter() - started)
        return HazardResult(
            analysis_id=analysis_id, hazard_type='flood', product_type='potential_detection',
            product_label=T.PRODUCT_LABEL['flood'], status='ok',
            aoi={'kind': area.kind, 'hectares': area.hectares, 'department': area.department,
                 'municipality': area.municipality},
            analysis_period={'windows': pre.date_windows, 'ratio_domain': params.ratio_domain},
            methodology=Methodology(name=M.METHOD_NAME, version=M.METHOD_VERSION, reference=M.REFERENCE),
            data_sources=M.DATA_SOURCES,
            resolution=Resolution(spatial_m=s1.MASK_SCALE_M, note='detection and area statistics at 10 m'),
            validation_status='under_validation',
            statistics={'primary_key': 'flood', 'primary_hectares': hectares, 'flood_hectares': hectares,
                        'flood_raw_hectares': raw_hectares, 'flood_pct_of_aoi': pct,
                        'otsu_threshold': threshold, 'ratio_domain': params.ratio_domain,
                        'scene_counts': pre.counts},
            layers=[layer.model_dump() for layer in layers], boundary=area.boundary, bounds=area.bounds,
            footprint_reference=reference, warnings=warnings,
            limitations=M.LIMITATIONS + [M.RATIO_NOTE], exposure_ready=True,
            generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            details={'scene_counts': pre.counts, 'date_windows': pre.date_windows,
                     'model_version': _model_version(params)},
            disclaimer=T.GENERAL_DISCLAIMER)

    def _layers(self, graph: dict, geometry, params: FloodParams, pre: PreflightResult):
        from .optical import s2_context_image
        images = dict(graph)
        have_context = pre.counts.get('s2_pre', 0) >= 1 and pre.counts.get('s2_post', 0) >= 1
        specs = LAYER_SPECS
        if have_context:
            images['s2_pre'] = s2_context_image(geometry, params.pre_start.isoformat(), params.pre_end.isoformat())
            images['s2_post'] = s2_context_image(geometry, params.post_start.isoformat(), params.post_end.isoformat())
        else:
            specs = [s for s in LAYER_SPECS if s[4] not in ('s2_pre', 's2_post')]
        return build_layers(images, specs)


