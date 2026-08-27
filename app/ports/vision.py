"""Port for structured image quality and defect analysis."""

from typing import Protocol, runtime_checkable

from app.platform.analysis import (
    ProviderMetadata,
    VisionAnalysisRequest,
    VisionAnalysisResult,
    VisionTask,
)


@runtime_checkable
class VisionProvider(Protocol):
    """Technology-neutral contract implemented by Vision adapters."""

    @property
    def provider_metadata(self) -> ProviderMetadata:
        """Return the configured provider and model deployment identity."""
        ...

    @property
    def analysis_task(self) -> VisionTask:
        """Return the image task this deployment is configured to execute."""
        ...

    def analyze_image(
        self,
        request: VisionAnalysisRequest,
        *,
        image: bytes,
    ) -> VisionAnalysisResult:
        """Analyze bounded image bytes loaded by Core from private storage."""
        ...
