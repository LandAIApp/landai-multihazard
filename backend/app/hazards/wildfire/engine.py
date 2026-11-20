"""Wildfire engine: a thin adapter around the EXISTING, unchanged V7.6 services.

``services.analysis.run_analysis`` / ``services.preflight.run_preflight`` remain the single implementation (and keep
serving the legacy /api/v1/wildfire/* routes). This class only translates their answers into the common hazard
contract; it never touches the science.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError, model_validator

from ...core.errors import InvalidRequestError
from ...schemas.common import (
    AnalysisRequest, DataSource, HazardInfo, HazardResult, Methodology, Notice, PreflightResult, Resolution,
)
from ...schemas.wildfire import AnalyzeResponse, PreflightResponse, WildfireRequest
from ...services.analysis import MODEL_VERSION, run_analysis
from ...services.preflight import run_preflight
from ..base import HazardEngine
from .. import terminology as T

METHODOLOGY = Methodology(name='FIRE FOREST COLOMBIA', version='V7.6 (Python port)',
                          reference='wildfire_gee_reference.js · docs/wildfire_gee_analysis.md')
SOURCES = [
    DataSource(name='Sentinel-2 SR Harmonized', role='PRE/POST composites and spectral indices',
               detail='Cloud Score+ and SCL cloud masking'),
    DataSource(name='VIIRS SNPP / NOAA-20 active fires', role='thermal evidence'),
    DataSource(name='Dynamic World / ESA WorldCover', role='land-cover and agricultural context'),
]
LIMITATIONS = [
    Notice(code='not_official_perimeter', message='The result is a preliminary estimate, not an official fire perimeter.'),
    Notice(code='likelihood_not_probability',
           message='The likelihood is a relative score from a Random Forest trained on automatic pseudolabels; it is not a '
                   'calibrated probability.'),
    Notice(code='equivalence_not_validated',
           message='Numerical equivalence with the original Google Earth Engine script has not been validated.'),
    Notice(code='custom_aoi_not_equivalent',
           message='Drawn areas run the same algorithm, but sampling, cleaning and VIIRS seeds depend on the study area.'),
]


class WildfireParams(BaseModel):
    """Wildfire parameters inside the common request: ``event_date`` (fire date) and ``analysis_end``."""

    event_date: date
    analysis_end: date

    @model_validator(mode='after')
    def _order(self) -> 'WildfireParams':
        if self.analysis_end < self.event_date:
            raise ValueError('analysis_end must be on or after event_date')
        return self


def to_legacy_request(req: AnalysisRequest) -> WildfireRequest:
    try:
        params = WildfireParams(**req.params)
        return WildfireRequest(department=req.department, municipality=req.municipality, geometry=req.geometry,
                               fire_date=params.event_date, analysis_end=params.analysis_end,
                               progress_id=req.progress_id)
    except ValidationError as exc:
        raise InvalidRequestError('The wildfire parameters are not valid: ' + '; '.join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())) from exc


def _notices(items) -> list[Notice]:
    return [Notice(code=i.code, message=i.message, params=dict(i.params)) for i in items]


class WildfireEngine(HazardEngine):
    hazard_id = 'wildfire'

    def info(self) -> HazardInfo:
        return HazardInfo(
            id='wildfire', module_status='operational', analysis_available=True, exposure_available=True,
            product_types=['potential_detection'], product_label=T.PRODUCT_LABEL['wildfire'],
            validation_status='operational_preliminary', methodology=METHODOLOGY, resolution_m=20,
            disclaimer=T.HAZARD_DISCLAIMER['wildfire'])

    def preflight(self, req: AnalysisRequest) -> PreflightResult:
        pf: PreflightResponse = run_preflight(to_legacy_request(req))
        windows = pf.date_windows.model_dump() if pf.date_windows is not None else {}
        return PreflightResult(
            hazard_type='wildfire', status=pf.status, valid=pf.valid, aoi_hectares=pf.aoi_hectares,
            aoi_kind=pf.aoi_kind,
            counts={'pre': pf.pre_count, 'post': pf.post_count, 'history': pf.history_count},
            date_windows=windows, warnings=_notices(pf.warnings), blocking_errors=_notices(pf.blocking_errors))

    def analyze(self, req: AnalysisRequest) -> HazardResult:
        legacy = to_legacy_request(req)
        res: AnalyzeResponse = run_analysis(legacy)
        return to_hazard_result(res, legacy)

    def get_metadata(self) -> dict[str, Any]:
        return {'methodology': METHODOLOGY.model_dump(), 'data_sources': [s.model_dump() for s in SOURCES],
                'limitations': [n.model_dump() for n in LIMITATIONS],
                'disclaimer': T.HAZARD_DISCLAIMER['wildfire'].model_dump()}


def to_hazard_result(res: AnalyzeResponse, legacy: WildfireRequest) -> HazardResult:
    probable = next((a for a in res.area_hectares if a.key == 'wf050'), None)
    return HazardResult(
        analysis_id=uuid.uuid4().hex, hazard_type='wildfire', product_type='potential_detection',
        product_label=T.PRODUCT_LABEL['wildfire'], status='ok',
        aoi=res.aoi or {'kind': legacy.aoi_kind}, 
        analysis_period={'event_date': legacy.fire_date.isoformat(), 'analysis_end': legacy.analysis_end.isoformat(),
                         'windows': res.date_windows.model_dump()},
        methodology=Methodology(name=METHODOLOGY.name, version=res.metadata.get('model_version', MODEL_VERSION),
                                reference=METHODOLOGY.reference),
        data_sources=SOURCES, resolution=Resolution(spatial_m=20, note='area statistics at 20 m'),
        validation_status='operational_preliminary',
        statistics={'primary_key': 'wf050', 'primary_hectares': probable.hectares if probable else None,
                    'area_statistics': res.area_statistics,
                    'area_hectares': [a.model_dump() for a in res.area_hectares]},
        layers=[layer.model_dump() for layer in res.layers], boundary=res.boundary, bounds=res.bounds,
        footprint_reference=res.analysis_ref, warnings=_notices(res.warnings), limitations=LIMITATIONS,
        generated_at=res.metadata.get('generated_at') or HazardResult.model_fields['generated_at'].default_factory(),
        exposure_ready=bool(res.analysis_ref),
        details={'image_counts': res.image_counts, 'training': res.training.model_dump(),
                 'metadata': res.metadata},
        disclaimer=T.GENERAL_DISCLAIMER)
