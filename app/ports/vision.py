"""Port for structured image quality and defect analysis."""

from typing import Protocol, runtime_checkable

from app.platform.analysis import (
    ProviderMetadata,
    VisionAnalysisRequest,
    VisionAnalysisResult,
)


@runtime_checkable
class VisionProvider(Protocol):
    """Technology-neutral contract implemented by Vision adapters."""

    @property
    def provider_metadata(self) -> ProviderMetadata:
        """Return the configured provider and model deployment identity."""
        ...

    def analyze_image(self, request: VisionAnalysisRequest) -> VisionAnalysisResult:
        """Analyze an object-storage reference; never receive raw image bytes."""
        ...
