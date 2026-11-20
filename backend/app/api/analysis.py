"""Common, hazard-agnostic analysis endpoints. The hazard is part of the request; engines are looked up in the registry."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.errors import AnalysisNotFoundError
from ..core.rate_limit import analyze_limit, limiter
from ..hazards import all_engines, get_engine
from ..schemas.common import AnalysisRequest, HazardInfo, HazardResult, PreflightResult
from ..services import analysis_registry

router = APIRouter(prefix='/api/v1', tags=['multi-hazard'])


@router.get('/hazards', response_model=list[HazardInfo])
def list_hazards() -> list[HazardInfo]:
    """Module status of every hazard (drives the selector and the landing cards; never starts any computation)."""
    return [engine.info() for engine in all_engines()]


@router.get('/hazards/{hazard}/metadata')
def hazard_metadata(hazard: str) -> dict:
    """Methodology, data sources, limitations and disclaimers of one hazard."""
    engine = get_engine(hazard)
    return {'info': engine.info().model_dump(), **engine.get_metadata()}


@router.post('/analysis/preflight', response_model=PreflightResult)
def preflight(payload: AnalysisRequest) -> PreflightResult:
    return get_engine(payload.hazard).preflight(payload)


@router.post('/analysis/run', response_model=HazardResult)
@limiter.limit(analyze_limit)
def run(request: Request, payload: AnalysisRequest) -> HazardResult:
    result = get_engine(payload.hazard).analyze(payload)
    analysis_registry.put(result)
    return result


@router.get('/analysis/{analysis_id}', response_model=HazardResult)
def get_analysis(analysis_id: str) -> HazardResult:
    result = analysis_registry.get(analysis_id)
    if result is None:
        raise AnalysisNotFoundError(
            'This analysis is not available on this server instance (results are kept for a short time only).')
    return result
