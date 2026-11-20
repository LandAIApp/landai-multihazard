"""Shared building blocks of the Multi-Hazard platform: area selection and the common hazard result contract.

Nothing here is hazard-specific. Every hazard engine returns a ``HazardResult``; the hazard-specific numbers live in
``statistics`` / ``details`` and the wording of the product (``product_label``) is supplied by the engine, so a flood
is never called a "burned" or a generic "affected" area.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

HazardType = Literal['wildfire', 'flood']
# What the number/map means. Never "risk" or "damage".
ProductType = Literal['observed_footprint', 'potential_detection', 'anomaly', 'susceptibility']
# Honest scientific status. Nothing is "validated" unless validation metrics have actually been computed.
ValidationStatus = Literal['operational_preliminary', 'experimental', 'under_validation', 'methodology_pending']
ModuleStatus = Literal['operational', 'experimental', 'in_development']

Position = Annotated[list[float], Field(min_length=2, max_length=3)]
Ring = Annotated[list[Position], Field(max_length=2000)]


class PolygonGeometry(BaseModel):
    """GeoJSON Polygon (EPSG:4326, [lon, lat]). Only Polygon is supported: MultiPolygon has not
    been verified through the Earth Engine graphs, so it is rejected by the schema."""

    type: Literal['Polygon']
    coordinates: Annotated[list[Ring], Field(min_length=1, max_length=5)]


class AreaSelection(BaseModel):
    """Study area EITHER by municipality OR by a drawn polygon (identical contract for every hazard)."""

    department: str | None = Field(None, min_length=1, max_length=120)
    municipality: str | None = Field(None, min_length=1, max_length=120)
    geometry: PolygonGeometry | None = None

    @model_validator(mode='after')
    def _one_area_source(self) -> 'AreaSelection':
        partial = bool(self.department) != bool(self.municipality)
        by_municipality = bool(self.department) and bool(self.municipality)
        by_geometry = self.geometry is not None
        if partial:
            raise ValueError('department and municipality must be provided together')
        if by_municipality and by_geometry:
            raise ValueError('conflicting area selection: send either department + municipality or geometry, not both')
        if not by_municipality and not by_geometry:
            raise ValueError('provide either department + municipality or a drawn geometry')
        return self

    @property
    def aoi_kind(self) -> str:
        return 'drawn' if self.geometry is not None else 'municipality'


class LocalizedText(BaseModel):
    en: str
    es: str


class Methodology(BaseModel):
    name: str
    version: str
    reference: str | None = None


class DataSource(BaseModel):
    name: str
    role: str                      # what the dataset is used for
    detail: str | None = None


class Resolution(BaseModel):
    spatial_m: float
    note: str | None = None


class Notice(BaseModel):
    """A warning or limitation: ``code`` lets the UI translate it, ``message`` is the English fallback."""

    code: str
    message: str
    params: dict[str, Any] = Field(default_factory=dict)


class HazardResult(BaseModel):
    """The common output contract (identical for wildfire and flood)."""

    analysis_id: str
    hazard_type: HazardType
    product_type: ProductType
    product_label: LocalizedText
    status: Literal['ok']
    aoi: dict[str, Any]
    analysis_period: dict[str, Any]
    methodology: Methodology
    data_sources: list[DataSource]
    resolution: Resolution
    validation_status: ValidationStatus
    statistics: dict[str, Any]
    layers: list[Any]
    boundary: dict[str, Any]
    bounds: list[list[float]]
    # Signed, backend-issued reference to the detected footprint (the Exposure step uses it; no client polygon).
    footprint_reference: str | None = None
    warnings: list[Notice] = []
    limitations: list[Notice] = []
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec='seconds'))
    exposure_ready: bool = False
    # Hazard-specific payload (counts of scenes, thresholds, ...). Never required by the common UI.
    details: dict[str, Any] = Field(default_factory=dict)
    disclaimer: LocalizedText | None = None


class HazardInfo(BaseModel):
    """What GET /api/v1/hazards says about each module (drives the hazard selector and the landing cards)."""

    id: HazardType
    module_status: ModuleStatus
    analysis_available: bool
    exposure_available: bool
    product_types: list[ProductType]
    product_label: LocalizedText
    validation_status: ValidationStatus
    methodology: Methodology | None = None
    resolution_m: float | None = None
    pending_reason: LocalizedText | None = None
    disclaimer: LocalizedText


class AnalysisRequest(AreaSelection):
    """Common request for POST /api/v1/analysis/preflight|run. ``params`` is validated by the hazard engine."""

    hazard: HazardType
    params: dict[str, Any] = Field(default_factory=dict)
    progress_id: str | None = Field(None, pattern=r'^[A-Za-z0-9_-]{16,64}$')


class PreflightResult(BaseModel):
    """Common preflight answer: data availability for the requested dates and area (never runs a model)."""

    hazard_type: HazardType
    status: Literal['ok', 'blocked']
    valid: bool
    aoi_hectares: float | None = None
    aoi_kind: Literal['municipality', 'drawn'] | None = None
    # Hazard-specific scene counts, e.g. wildfire {pre, post, history}; flood {s1_pre, s1_post, s2_pre, s2_post}.
    counts: dict[str, int | None] = Field(default_factory=dict)
    date_windows: dict[str, Any] = Field(default_factory=dict)
    warnings: list[Notice] = []
    blocking_errors: list[Notice] = []
