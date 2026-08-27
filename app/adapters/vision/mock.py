"""Deterministic, network-free Vision adapter used in Sprint 0."""

import hashlib
from enum import StrEnum

from pydantic import ValidationError

from app.platform.analysis import (
    BoundingBox,
    CoordinateSystem,
    DefectType,
    DetectionFinding,
    ImageQualityRejectionReason,
    ImageQualityResult,
    ImageUsability,
    MockProviderMode,
    ProviderFailureError,
    ProviderMetadata,
    ProviderSchemaError,
    VisionAnalysisRequest,
    VisionAnalysisResult,
    VisionImageAssessment,
    VisionImageAssessmentOutcome,
    VisionInvalidStructuredOutputError,
    VisionProviderRequestRejectedError,
    VisionProviderTimeoutError,
    VisionProviderUnavailableError,
    VisionTask,
)


class VisionMockMode(StrEnum):
    """Deterministic Sprint 3 scenarios for workflow and contract testing."""

    SUCCESS_SINGLE_DEFECT = "success_single_defect"
    SUCCESS_MULTIPLE_DEFECTS = "success_multiple_defects"
    NO_DEFECT = "no_defect"
    LOW_QUALITY_IMAGE = "low_quality_image"
    EMPTY_DETECTIONS = "empty_detections"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_GEOMETRY = "invalid_geometry"
    BINARY_CANDIDATE = "binary_candidate"
    BINARY_BELOW_THRESHOLD = "binary_below_threshold"


class MockVisionProvider:
    """A deterministic Vision fake that never resolves or fetches image references."""

    def __init__(
        self,
        *,
        mode: MockProviderMode | VisionMockMode | str = VisionMockMode.SUCCESS_SINGLE_DEFECT,
        model_name: str = "csight-mock-vision",
        model_version: str = "0.1.0",
        analysis_task: VisionTask | str | None = None,
        assessment_threshold: float | None = None,
    ) -> None:
        normalized_mode = mode.replace("-", "_")
        if normalized_mode == MockProviderMode.SUCCESS.value:
            self._mode = VisionMockMode.SUCCESS_SINGLE_DEFECT
        elif normalized_mode in {
            MockProviderMode.FAILURE.value,
            MockProviderMode.SCHEMA_ERROR.value,
        }:
            self._mode = MockProviderMode(normalized_mode)
        else:
            self._mode = VisionMockMode(normalized_mode)
        binary_mode = self._mode in {
            VisionMockMode.BINARY_CANDIDATE,
            VisionMockMode.BINARY_BELOW_THRESHOLD,
        }
        if binary_mode and assessment_threshold is None:
            raise ValueError("assessment_threshold is required for a binary mock mode")
        if assessment_threshold is not None and (
            isinstance(assessment_threshold, bool) or not 0.0 <= assessment_threshold <= 1.0
        ):
            raise ValueError("assessment_threshold must be between zero and one")
        if self._mode is VisionMockMode.BINARY_BELOW_THRESHOLD and assessment_threshold == 0.0:
            raise ValueError("binary_below_threshold requires a positive threshold")
        configured_task = (
            VisionTask(analysis_task)
            if analysis_task is not None
            else (
                VisionTask.ANY_DEFECT_CLASSIFICATION
                if binary_mode
                else VisionTask.QUALITY_AND_DEFECT_DETECTION
            )
        )
        if binary_mode is not (configured_task is VisionTask.ANY_DEFECT_CLASSIFICATION):
            raise ValueError("mock Vision mode and analysis task must describe the same contract")
        self._assessment_threshold = assessment_threshold
        self._analysis_task = configured_task
        self._metadata = ProviderMetadata(
            provider="mock",
            name=model_name,
            version=model_version,
            preprocess_version="1.0",
        )

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return self._metadata

    @property
    def analysis_task(self) -> VisionTask:
        return self._analysis_task

    def analyze_image(
        self,
        request: VisionAnalysisRequest,
        *,
        image: bytes = b"csight-mock-image",
    ) -> VisionAnalysisResult:
        if not image:
            raise ProviderSchemaError(
                provider=self._metadata.provider,
                message="mock Vision received an empty image",
            )
        if request.task is not self._analysis_task:
            raise VisionProviderRequestRejectedError(
                provider=self._metadata.provider,
                message="mock Vision request task does not match its configured assessment mode",
            )
        self._raise_configured_failure()
        if self._mode in {MockProviderMode.SCHEMA_ERROR, VisionMockMode.INVALID_SCHEMA}:
            self._raise_schema_error(
                request,
                canonical=self._mode is VisionMockMode.INVALID_SCHEMA,
            )
        if self._mode is VisionMockMode.INVALID_GEOMETRY:
            self._raise_geometry_error()

        fingerprint = hashlib.sha256(
            f"{request.evidence_id or request.image_reference}\0{request.content_type}\0"
            f"{request.task.value}".encode()
            + image
        ).digest()
        offset = fingerprint[0] / 2550
        confidence = round(0.80 + fingerprint[1] / 2550, 4)
        quality_score = round(0.85 + fingerprint[2] / 2550, 4)

        quality = ImageQualityResult(
            usable=ImageUsability.USABLE,
            blurred=False,
            dark=False,
            overexposed=False,
            product_visible=True,
            defect_area_visible=True,
            score=quality_score,
        )
        if self._mode is VisionMockMode.LOW_QUALITY_IMAGE:
            quality = ImageQualityResult(
                usable=ImageUsability.NOT_USABLE,
                blurred=True,
                dark=False,
                overexposed=False,
                product_visible=True,
                defect_area_visible=False,
                score=0.2,
                rejection_reasons=(
                    ImageQualityRejectionReason.BLURRED,
                    ImageQualityRejectionReason.DEFECT_AREA_NOT_VISIBLE,
                ),
            )
        detections = (
            DetectionFinding(
                id="detection-0",
                label=DefectType.LEAKAGE,
                model_class_id="4",
                model_class_name="spillage",
                confidence=confidence,
                geometry=BoundingBox(
                    coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
                    x1=round(0.20 + offset, 4),
                    y1=0.40,
                    x2=round(0.70 + offset, 4),
                    y2=0.90,
                ),
            ),
        )
        if self._mode is VisionMockMode.SUCCESS_MULTIPLE_DEFECTS:
            detections += (
                DetectionFinding(
                    id="detection-1",
                    label=DefectType.DENT,
                    model_class_id="1",
                    model_class_name="deformation",
                    confidence=round(max(0.0, confidence - 0.1), 4),
                    geometry=BoundingBox(
                        coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
                        x1=0.05,
                        y1=0.10,
                        x2=0.30,
                        y2=0.35,
                    ),
                ),
            )
        if self._mode in {
            VisionMockMode.NO_DEFECT,
            VisionMockMode.EMPTY_DETECTIONS,
            VisionMockMode.LOW_QUALITY_IMAGE,
        }:
            detections = ()

        image_assessment = None
        is_binary = self._mode in {
            VisionMockMode.BINARY_CANDIDATE,
            VisionMockMode.BINARY_BELOW_THRESHOLD,
        }
        if is_binary:
            detections = ()
            quality = ImageQualityResult(usable=ImageUsability.NOT_EVALUATED)
            threshold = self._assessment_threshold
            if threshold is None:
                raise AssertionError("binary mock threshold was not configured")
            if self._mode is VisionMockMode.BINARY_CANDIDATE:
                score = threshold + ((1.0 - threshold) * (0.25 + fingerprint[1] / 510))
            else:
                score = threshold * (0.25 + fingerprint[1] / 510)
            score = round(min(1.0, max(0.0, score)), 6)
            outcome = (
                VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE
                if score >= threshold
                else VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD
            )
            image_assessment = VisionImageAssessment(
                score=score,
                threshold=threshold,
                outcome=outcome,
            )

        return VisionAnalysisResult(
            provider_name=self._metadata.provider,
            model_name=self._metadata.name,
            model_version=self._metadata.version,
            model_revision=self._metadata.revision,
            dataset_version="synthetic-any-defect-v1" if is_binary else "synthetic-v1",
            taxonomy_version=(
                "csight-any-defect-assessment-v1" if is_binary else "csight-defect-v1"
            ),
            threshold_version=(
                "synthetic-mock-any-defect-threshold-v1" if is_binary else "mock-threshold-v1"
            ),
            preprocess_version=self._metadata.preprocess_version or "mock-preprocess-v1",
            postprocess_version="mock-postprocess-v1",
            runtime="python",
            precision="deterministic",
            image_width=request.image_width,
            image_height=request.image_height,
            image_reference=request.image_reference,
            image_quality=quality,
            detections=detections,
            image_assessment=image_assessment,
            latency_ms=20 + fingerprint[3] % 31,
        )

    def _raise_configured_failure(self) -> None:
        if self._mode is VisionMockMode.TIMEOUT:
            raise VisionProviderTimeoutError(
                provider=self._metadata.provider,
                message="mock Vision deadline exceeded",
            )
        if self._mode is MockProviderMode.FAILURE:
            raise ProviderFailureError(
                provider=self._metadata.provider,
                message="mock Vision inference failed",
            )
        if self._mode is VisionMockMode.TRANSIENT_ERROR:
            raise VisionProviderUnavailableError(
                provider=self._metadata.provider,
                message="mock Vision service is temporarily unavailable",
            )
        if self._mode is VisionMockMode.PERMANENT_ERROR:
            raise VisionProviderRequestRejectedError(
                provider=self._metadata.provider,
                message="mock Vision permanently rejected the image",
            )

    def _raise_schema_error(self, request: VisionAnalysisRequest, *, canonical: bool) -> None:
        try:
            VisionAnalysisResult.model_validate(
                {
                    "schema_version": "1.0",
                    "provider_name": self._metadata.provider,
                    "model_name": self._metadata.name,
                    "model_version": self._metadata.version,
                    "model_revision": self._metadata.revision,
                    "taxonomy_version": "csight-defect-v1",
                    "threshold_version": "mock-threshold-v1",
                    "preprocess_version": "mock-preprocess-v1",
                    "postprocess_version": "mock-postprocess-v1",
                    "image_width": request.image_width,
                    "image_height": request.image_height,
                    "image_quality": {
                        "usable": "USABLE",
                        "blurred": False,
                        "dark": False,
                        "overexposed": False,
                        "product_visible": True,
                        "defect_area_visible": True,
                        "score": 1.2,
                    },
                    "detections": [],
                    "latency_ms": 1,
                }
            )
        except ValidationError as error:
            error_type = VisionInvalidStructuredOutputError if canonical else ProviderSchemaError
            raise error_type(
                provider=self._metadata.provider,
                message="mock Vision response violated the common schema",
            ) from error
        raise AssertionError("mock schema-error payload unexpectedly validated")

    def _raise_geometry_error(self) -> None:
        try:
            BoundingBox(
                coordinate_system=CoordinateSystem.NORMALIZED_XYXY,
                x1=0.8,
                y1=0.2,
                x2=0.1,
                y2=0.7,
            )
        except ValidationError as error:
            raise VisionInvalidStructuredOutputError(
                provider=self._metadata.provider,
                message="mock Vision returned invalid geometry",
            ) from error
        raise AssertionError("mock invalid geometry unexpectedly validated")
