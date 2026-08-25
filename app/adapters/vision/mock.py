"""Deterministic, network-free Vision adapter used in Sprint 0."""

import hashlib

from pydantic import ValidationError

from app.platform.analysis import (
    BoundingBox,
    DefectType,
    DetectionFinding,
    ImageQualityResult,
    MockProviderMode,
    ProviderFailureError,
    ProviderMetadata,
    ProviderSchemaError,
    ProviderTimeoutError,
    VisionAnalysisRequest,
    VisionAnalysisResult,
)


class MockVisionProvider:
    """A deterministic Vision fake that never resolves or fetches image references."""

    def __init__(
        self,
        *,
        mode: MockProviderMode | str = MockProviderMode.SUCCESS,
        model_name: str = "csight-mock-vision",
        model_version: str = "0.1.0",
    ) -> None:
        normalized_mode = mode.replace("-", "_")
        self._mode = MockProviderMode(normalized_mode)
        self._metadata = ProviderMetadata(
            provider="mock",
            name=model_name,
            version=model_version,
            preprocess_version="1.0",
        )

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return self._metadata

    def analyze_image(self, request: VisionAnalysisRequest) -> VisionAnalysisResult:
        self._raise_configured_failure()
        if self._mode is MockProviderMode.SCHEMA_ERROR:
            self._raise_schema_error(request)

        fingerprint = hashlib.sha256(
            f"{request.case_id}\0{request.image_reference}\0{request.task.value}".encode()
        ).digest()
        offset = fingerprint[0] / 2550
        confidence = round(0.80 + fingerprint[1] / 2550, 4)
        quality_score = round(0.85 + fingerprint[2] / 2550, 4)

        return VisionAnalysisResult(
            model=self._metadata,
            image_reference=request.image_reference,
            image_quality=ImageQualityResult(
                blurred=False,
                too_dark=False,
                product_visible=True,
                defect_area_visible=True,
                score=quality_score,
            ),
            detections=(
                DetectionFinding(
                    label=DefectType.LEAKAGE,
                    confidence=confidence,
                    geometry=BoundingBox(
                        x1=round(0.20 + offset, 4),
                        y1=0.40,
                        x2=round(0.70 + offset, 4),
                        y2=0.90,
                    ),
                ),
            ),
            latency_ms=20 + fingerprint[3] % 31,
        )

    def _raise_configured_failure(self) -> None:
        if self._mode is MockProviderMode.TIMEOUT:
            raise ProviderTimeoutError(
                provider=self._metadata.provider,
                message="mock Vision deadline exceeded",
            )
        if self._mode is MockProviderMode.FAILURE:
            raise ProviderFailureError(
                provider=self._metadata.provider,
                message="mock Vision inference failed",
            )

    def _raise_schema_error(self, request: VisionAnalysisRequest) -> None:
        try:
            VisionAnalysisResult.model_validate(
                {
                    "schema_version": "1.0",
                    "model": self._metadata.model_dump(),
                    "image_reference": request.image_reference,
                    "image_quality": {
                        "blurred": False,
                        "too_dark": False,
                        "product_visible": True,
                        "defect_area_visible": True,
                        "score": 1.2,
                    },
                    "detections": [],
                    "latency_ms": 1,
                }
            )
        except ValidationError as error:
            raise ProviderSchemaError(
                provider=self._metadata.provider,
                message="mock Vision response violated the common schema",
            ) from error
        raise AssertionError("mock schema-error payload unexpectedly validated")
