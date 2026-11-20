from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .common import AreaSelection, Position, PolygonGeometry, Ring  # noqa: F401  (re-exported: public import path)


class WildfireRequest(AreaSelection):
    """Select the study area EITHER by municipality (original contract) OR by a drawn polygon."""

    fire_date: date
    analysis_end: date
    # Random id chosen by the client so it can poll GET /api/v1/progress/{id} while the analysis runs.
    progress_id: str | None = Field(None, pattern=r'^[A-Za-z0-9_-]{16,64}$')

    @model_validator(mode='after')
    def _check_order(self) -> 'WildfireRequest':
        if self.analysis_end < self.fire_date:
            raise ValueError('analysis_end must be on or after fire_date')
        return self


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class DateWindows(BaseModel):
    pre: DateRange
    post: DateRange
    history: DateRange


class Issue(BaseModel):
    code: str
    message: str
    params: dict[str, Any] = Field(default_factory=dict)


class PreflightResponse(BaseModel):
    status: Literal['ok', 'blocked']
    valid: bool
    pre_count: int | None = None
    post_count: int | None = None
    history_count: int | None = None
    date_windows: DateWindows | None = None
    aoi_hectares: float | None = None
    aoi_kind: Literal['municipality', 'drawn'] | None = None
    warnings: list[Issue] = []
    blocking_errors: list[Issue] = []


class AreaEntry(BaseModel):
    threshold: float
    key: str
    label: str
    hectares: float


class LegendInfo(BaseModel):
    type: Literal['gradient', 'solid', 'rgb']
    min: float | None = None
    max: float | None = None
    colors: list[str] = []


class LayerInfo(BaseModel):
    id: str
    label: str
    group: str
    description: str
    tile_url: str
    visible_by_default: bool
    legend: LegendInfo | None = None


class TrainingInfo(BaseModel):
    positive_samples: int
    negative_samples: int
    note: str


class AnalyzeResponse(BaseModel):
    status: Literal['ok']
    metadata: dict[str, Any]
    image_counts: dict[str, int]
    date_windows: DateWindows
    training: TrainingInfo
    area_statistics: dict[str, float]
    area_hectares: list[AreaEntry]
    layers: list[LayerInfo]
    boundary: dict[str, Any]
    bounds: list[list[float]]
    warnings: list[Issue] = []
    # Added in v2 (optional, backwards compatible): signed reference to this analysis for the
    # Exposure module, and the kind/size of the study area.
    analysis_ref: str | None = None
    aoi: dict[str, Any] | None = None
