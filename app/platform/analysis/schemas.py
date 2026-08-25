"""Strict Pydantic contracts shared by AI ports, adapters, and use cases."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.analysis.enums import (
    CoordinateSystem,
    CustomerRequest,
    DefectLocation,
    DefectType,
    GeometryType,
    VisionTask,
)

SCHEMA_VERSION = "1.0"
type ScalarAttribute = str | int | float | bool | None


class AnalysisContract(BaseModel):
    """Base configuration for immutable, fail-closed provider contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProviderMetadata(AnalysisContract):
    """Identifies the provider deployment that produced an analysis."""

    provider: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    preprocess_version: str | None = Field(default=None, min_length=1)


class AnalysisVersionReferences(AnalysisContract):
    """Version snapshot retained with an append-only analysis run.

    Policy, threshold, and retrieval fields are nullable in Sprint 0 because those
    evaluators have not run yet. Once applied, their concrete versions can be
    captured without changing the provider contracts.
    """

    llm_model: ProviderMetadata
    vision_model: ProviderMetadata
    prompt_version: str = Field(min_length=1)
    policy_version: str | None = Field(default=None, min_length=1)
    threshold_version: str | None = Field(default=None, min_length=1)
    embedding_model_version: str | None = Field(default=None, min_length=1)
    retrieval_index_version: str | None = Field(default=None, min_length=1)


class LLMAnalysisRequest(AnalysisContract):
    """Structured input accepted by every LLM provider implementation."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    customer_message: str = Field(min_length=1)
    requested_action: CustomerRequest = CustomerRequest.UNSPECIFIED
    prompt_version: str = Field(default="sprint-0", min_length=1)
    attributes: dict[str, ScalarAttribute] = Field(default_factory=dict)


class LLMClaim(AnalysisContract):
    type: DefectType
    description: str = Field(min_length=1)


class LLMCaseExtraction(AnalysisContract):
    """Normalized extraction only; it deliberately contains no final decision."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    model: ProviderMetadata
    issue_type: DefectType
    claimed_location: DefectLocation
    customer_request: CustomerRequest
    claims: tuple[LLMClaim, ...] = ()
    missing_information: tuple[str, ...] = ()
    summary: str = Field(min_length=1)


class VisionAnalysisRequest(AnalysisContract):
    """A reference-only image request; binary data never crosses the queue boundary."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    image_reference: str = Field(min_length=1)
    task: VisionTask = VisionTask.QUALITY_AND_DEFECT_DETECTION


class BoundingBox(AnalysisContract):
    """Normalized coordinates for a provider-independent detection geometry."""

    type: Literal[GeometryType.BOUNDING_BOX] = GeometryType.BOUNDING_BOX
    coordinate_system: Literal[CoordinateSystem.NORMALIZED] = CoordinateSystem.NORMALIZED
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_corner_order(self) -> "BoundingBox":
        if self.x2 <= self.x1:
            raise ValueError("x2 must be greater than x1")
        if self.y2 <= self.y1:
            raise ValueError("y2 must be greater than y1")
        return self


class ImageQualityResult(AnalysisContract):
    blurred: bool
    too_dark: bool
    product_visible: bool
    defect_area_visible: bool
    score: float = Field(ge=0.0, le=1.0)


class DetectionFinding(AnalysisContract):
    """A detection already mapped from provider-specific class IDs."""

    label: DefectType
    confidence: float = Field(ge=0.0, le=1.0)
    geometry: BoundingBox


class VisionAnalysisResult(AnalysisContract):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    model: ProviderMetadata
    image_reference: str = Field(min_length=1)
    image_quality: ImageQualityResult
    detections: tuple[DetectionFinding, ...] = ()
    latency_ms: int = Field(ge=0)
