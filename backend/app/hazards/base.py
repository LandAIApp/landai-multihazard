"""Hazard engine interface.

Every hazard exposes the same five operations; the scientific implementations stay completely independent.
The shared services (Earth Engine bootstrap, AOI handling, exposure, rate limiting, cache, errors) live outside this
package and know nothing about any specific hazard.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..schemas.common import AnalysisRequest, HazardInfo, HazardResult, PreflightResult


class HazardEngine(ABC):
    hazard_id: str

    @abstractmethod
    def info(self) -> HazardInfo:
        """Static description of the module: status, product types, validation status, terminology."""

    @abstractmethod
    def preflight(self, req: AnalysisRequest) -> PreflightResult:
        """Data availability for the request. Must not run the scientific model."""

    @abstractmethod
    def analyze(self, req: AnalysisRequest) -> HazardResult:
        """Run the hazard analysis. Engines without a validated method raise MethodologyUnavailableError."""

    def get_layers(self, result: HazardResult) -> list[Any]:
        return result.layers

    def get_statistics(self, result: HazardResult) -> dict[str, Any]:
        return result.statistics

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Methodology, data sources, limitations and disclaimers (the UI shows these in the methodology panel)."""
