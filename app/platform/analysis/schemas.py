"""Strict Pydantic contracts shared by AI ports, adapters, and use cases."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis.enums import (
    CoordinateSystem,
    CustomerRequest,
    DefectLocation,
    DefectType,
    ExtractedRequestedAction,
    ExtractionIssueType,
    GeometryType,
    ImageQualityRejectionReason,
    ImageUsability,
    MissingInformation,
    VisionImageAssessmentOutcome,
    VisionImageAssessmentType,
    VisionTask,
    VisionThresholdOperator,
)
from app.platform.analysis.errors import LLMSourceQuoteMismatchError
from app.platform.analysis.models import ProviderExecutionMetadata

SCHEMA_VERSION = "1.0"
MAX_LLM_INPUT_CHARS = 20_000
MAX_LLM_OUTPUT_CHARS = 32_000
MAX_LLM_REFERENCE_CHARS = 200
MAX_LLM_SUMMARY_CHARS = 2_000
MAX_LLM_CLAIM_DESCRIPTION_CHARS = 2_000
MAX_LLM_SOURCE_QUOTE_CHARS = 2_000
MAX_LLM_CLAIMS = 50
MAX_LLM_ISSUE_TYPES = 20
MAX_LLM_MISSING_INFORMATION = 20
type ScalarAttribute = str | int | float | bool | None


class AnalysisContract(BaseModel):
    """Base configuration for immutable, fail-closed provider contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProviderMetadata(AnalysisContract):
    """Identifies the provider deployment that produced an analysis."""

    provider: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    revision: str | None = Field(default=None, min_length=1)
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


class LLMTextExtractionRequest(AnalysisContract):
    """Allowlisted customer data sent to the text-extraction provider.

    Internal IDs, arbitrary Case attributes, credentials, and evidence references
    intentionally have no fields in this model.
    """

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    customer_message: str = Field(min_length=1, max_length=MAX_LLM_INPUT_CHARS, repr=False)
    order_ref: str = Field(min_length=1, max_length=MAX_LLM_REFERENCE_CHARS)
    product_ref: str = Field(min_length=1, max_length=MAX_LLM_REFERENCE_CHARS)
    requested_action: CustomerRequest = CustomerRequest.UNSPECIFIED

    @field_validator("customer_message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("customer_message must not be blank")
        return normalized


class LLMTextClaim(AnalysisContract):
    type: ExtractionIssueType
    location: DefectLocation = DefectLocation.UNKNOWN
    description: str = Field(min_length=1, max_length=MAX_LLM_CLAIM_DESCRIPTION_CHARS)
    source_quote: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_LLM_SOURCE_QUOTE_CHARS,
        repr=False,
    )


class LLMTextExtractionResult(AnalysisContract):
    """Decision-free, persistable structured extraction for Sprint 2."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    language: str = Field(default="ko", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    issue_types: tuple[ExtractionIssueType, ...] = Field(
        min_length=1,
        max_length=MAX_LLM_ISSUE_TYPES,
    )
    claims: tuple[LLMTextClaim, ...] = Field(default=(), max_length=MAX_LLM_CLAIMS)
    requested_action: ExtractedRequestedAction
    missing_information: tuple[MissingInformation, ...] = Field(
        default=(),
        max_length=MAX_LLM_MISSING_INFORMATION,
    )
    summary: str = Field(min_length=1, max_length=MAX_LLM_SUMMARY_CHARS)

    @model_validator(mode="after")
    def validate_normalized_collections(self) -> "LLMTextExtractionResult":
        if len(set(self.issue_types)) != len(self.issue_types):
            raise ValueError("issue_types must not contain duplicates")
        if len(set(self.missing_information)) != len(self.missing_information):
            raise ValueError("missing_information must not contain duplicates")
        unlisted_claim_types = {claim.type for claim in self.claims} - set(self.issue_types)
        if unlisted_claim_types:
            raise ValueError("every claim type must also appear in issue_types")
        if len(self.model_dump_json()) > MAX_LLM_OUTPUT_CHARS:
            raise ValueError("structured extraction exceeds the output character limit")
        return self

    def require_exact_source_quotes(
        self,
        *,
        customer_message: str,
        provider: str,
    ) -> None:
        """Require every supplied quote to be an exact contiguous input substring."""

        for claim in self.claims:
            if claim.source_quote is not None and claim.source_quote not in customer_message:
                raise LLMSourceQuoteMismatchError(
                    provider=provider,
                    message="a source quote was not an exact customer-message substring",
                )


class LLMTextExtractionResponse(AnalysisContract):
    result: LLMTextExtractionResult
    metadata: ProviderExecutionMetadata


class LLMExtractionResultRecord(AnalysisContract):
    """Append-only persistence value for one successful text-extraction stage."""

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    result: LLMTextExtractionResult
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class AnalysisRequestedEvent(AnalysisContract):
    """Reference-only queue event; customer content cannot be represented."""

    event_id: str = Field(min_length=1)
    event_type: Literal["analysis.requested.v1"] = "analysis.requested.v1"
    event_version: Literal["1.0"] = "1.0"
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)

    def queue_payload(self) -> dict[str, str]:
        """Return exactly the six reference IDs permitted in the Celery payload."""

        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "analysis_run_id": self.analysis_run_id,
            "stage_run_id": self.stage_run_id,
            "correlation_id": self.correlation_id,
        }


class VisionAnalysisRequest(AnalysisContract):
    """Safe metadata passed beside image bytes at the provider port."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    evidence_id: str | None = Field(default=None, min_length=1)
    content_type: str = Field(default="image/png", min_length=1, max_length=127)
    image_width: int = Field(default=1, gt=0)
    image_height: int = Field(default=1, gt=0)
    case_id: str | None = Field(default=None, min_length=1, deprecated=True)
    image_reference: str | None = Field(default=None, min_length=1, deprecated=True)
    task: VisionTask = VisionTask.QUALITY_AND_DEFECT_DETECTION

    @model_validator(mode="after")
    def require_evidence_identity(self) -> "VisionAnalysisRequest":
        if self.evidence_id is None and self.image_reference is None:
            raise ValueError("evidence_id is required")
        return self


class BoundingBox(AnalysisContract):
    """Normalized coordinates for a provider-independent detection geometry."""

    type: Literal[GeometryType.BOUNDING_BOX] = GeometryType.BOUNDING_BOX
    coordinate_system: CoordinateSystem = CoordinateSystem.NORMALIZED
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
    usable: ImageUsability
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    blurred: bool | None = None
    dark: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("dark", "too_dark"),
    )
    overexposed: bool | None = None
    product_visible: bool | None = None
    defect_area_visible: bool | None = None
    rejection_reasons: tuple[ImageQualityRejectionReason, ...] = ()

    @model_validator(mode="after")
    def validate_quality_state(self) -> "ImageQualityResult":
        if len(set(self.rejection_reasons)) != len(self.rejection_reasons):
            raise ValueError("rejection_reasons must not contain duplicates")
        if self.usable is ImageUsability.NOT_EVALUATED and any(
            value is not None
            for value in (
                self.score,
                self.blurred,
                self.dark,
                self.overexposed,
                self.product_visible,
                self.defect_area_visible,
            )
        ):
            raise ValueError("NOT_EVALUATED quality fields must remain null")
        return self


class DetectionFinding(AnalysisContract):
    """A detection already mapped from provider-specific class IDs."""

    id: str = Field(default="detection-0", min_length=1, max_length=100)
    label: DefectType
    model_class_id: str | None = Field(default=None, min_length=1, max_length=100)
    model_class_name: str | None = Field(default=None, min_length=1, max_length=255)
    confidence: float = Field(ge=0.0, le=1.0)
    geometry: BoundingBox


class VisionImageAssessment(AnalysisContract):
    """One non-localizing any-defect score and its frozen operating threshold.

    This is an image-level routing signal.  It cannot identify a defect type or
    location, and a score below the threshold is not evidence that the image is
    normal.
    """

    assessment_type: Literal[VisionImageAssessmentType.ANY_DEFECT] = (
        VisionImageAssessmentType.ANY_DEFECT
    )
    model_output_name: Literal["defect"] = "defect"
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    threshold_operator: Literal[VisionThresholdOperator.GREATER_THAN_OR_EQUAL] = (
        VisionThresholdOperator.GREATER_THAN_OR_EQUAL
    )
    outcome: VisionImageAssessmentOutcome

    @model_validator(mode="after")
    def require_outcome_to_match_frozen_threshold(self) -> "VisionImageAssessment":
        expected = (
            VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE
            if self.score >= self.threshold
            else VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD
        )
        if self.outcome is not expected:
            raise ValueError("outcome must match score >= threshold")
        return self


class VisionAnalysisResult(AnalysisContract):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    provider_name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=100)
    model_revision: str | None = Field(default=None, min_length=1, max_length=255)
    dataset_version: str | None = Field(default=None, min_length=1, max_length=100)
    taxonomy_version: str = Field(min_length=1, max_length=100)
    threshold_version: str = Field(min_length=1, max_length=100)
    preprocess_version: str = Field(min_length=1, max_length=100)
    postprocess_version: str = Field(min_length=1, max_length=100)
    framework: str | None = Field(default=None, min_length=1, max_length=100)
    runtime: str | None = Field(default=None, min_length=1, max_length=100)
    precision: str | None = Field(default=None, min_length=1, max_length=100)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    image_reference: str | None = Field(default=None, min_length=1, deprecated=True)
    image_quality: ImageQualityResult
    detections: tuple[DetectionFinding, ...] = ()
    image_assessment: VisionImageAssessment | None = None
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def separate_detection_from_image_level_assessment(self) -> "VisionAnalysisResult":
        if self.image_assessment is not None and self.detections:
            raise ValueError("image-level assessment and localized detections are separate modes")
        return self

    @property
    def model(self) -> ProviderMetadata:
        """Compatibility projection for the original Sprint 0 provider contract."""

        return ProviderMetadata(
            provider=self.provider_name,
            name=self.model_name,
            version=self.model_version,
            revision=self.model_revision,
            preprocess_version=self.preprocess_version,
        )


class AnalysisEvidenceSnapshot(AnalysisContract):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    position: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_snapshot_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class VisionAnalysisResultRecord(AnalysisContract):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    result: VisionAnalysisResult
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_result_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)
