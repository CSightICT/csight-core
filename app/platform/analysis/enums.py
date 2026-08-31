"""Technology-agnostic enums shared by AI analysis contracts."""

from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.platform.analysis.errors import InvalidAnalysisTransitionError

TEXT_EXTRACTION_PIPELINE_VERSION: Final = "1.0.0"
TEXT_EXTRACTION_PROMPT_VERSION: Final = "1.0.1"
TEXT_EXTRACTION_INPUT_SCHEMA_VERSION: Final = "1.0"
TEXT_EXTRACTION_OUTPUT_SCHEMA_VERSION: Final = "1.0"
TEXT_EXTRACTION_V2_PIPELINE_VERSION: Final = "2.0.0"
TEXT_EXTRACTION_V2_PROMPT_VERSION: Final = "2.0.0"
TEXT_EXTRACTION_V2_INPUT_SCHEMA_VERSION: Final = "2.0"
TEXT_EXTRACTION_V2_OUTPUT_SCHEMA_VERSION: Final = "2.0"
MULTIMODAL_ANALYSIS_PIPELINE_VERSION: Final = "1.0.0"
VISION_INPUT_SCHEMA_VERSION: Final = "1.0"
VISION_OUTPUT_SCHEMA_VERSION: Final = "1.0"


class DefectType(StrEnum):
    """Normalized product-defect taxonomy used at the provider boundary."""

    LEAKAGE = "LEAKAGE"
    CONTAINER_DAMAGE = "CONTAINER_DAMAGE"
    DENT = "DENT"
    CRACK = "CRACK"
    SCRATCH = "SCRATCH"
    DISCOLORATION = "DISCOLORATION"
    MISSING_PART = "MISSING_PART"
    BREAKAGE = "BREAKAGE"
    MISSING_COMPONENT = "MISSING_COMPONENT"
    FUNCTIONAL_FAILURE = "FUNCTIONAL_FAILURE"
    PACKAGING_DAMAGE = "PACKAGING_DAMAGE"
    CONTAMINATION = "CONTAMINATION"
    SURFACE_DAMAGE = "SURFACE_DAMAGE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ExtractionIssueType(StrEnum):
    """Exact Sprint 2 issue taxonomy for persisted text extraction."""

    DENT = "DENT"
    CRACK = "CRACK"
    BREAKAGE = "BREAKAGE"
    LEAKAGE = "LEAKAGE"
    MISSING_COMPONENT = "MISSING_COMPONENT"
    WRONG_ITEM = "WRONG_ITEM"
    CONTAMINATION = "CONTAMINATION"
    FUNCTIONAL_FAILURE = "FUNCTIONAL_FAILURE"
    PACKAGING_DAMAGE = "PACKAGING_DAMAGE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DefectLocation(StrEnum):
    """Coarse, provider-independent location for an observed or claimed defect."""

    TOP = "TOP"
    BOTTOM = "BOTTOM"
    SIDE = "SIDE"
    FRONT = "FRONT"
    BACK = "BACK"
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    MULTIPLE = "MULTIPLE"
    UNKNOWN = "UNKNOWN"


class CustomerRequest(StrEnum):
    """A customer's stated request; this is not a final business decision."""

    EXCHANGE = "EXCHANGE"
    REFUND = "REFUND"
    RETURN = "RETURN"
    REPAIR = "REPAIR"
    INFORMATION = "INFORMATION"
    OTHER = "OTHER"
    UNSPECIFIED = "UNSPECIFIED"


class ExtractedRequestedAction(StrEnum):
    """Action explicitly extracted from text, never a business decision."""

    REFUND = "REFUND"
    EXCHANGE = "EXCHANGE"
    RESHIPMENT = "RESHIPMENT"
    REPAIR = "REPAIR"
    INFORMATION = "INFORMATION"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class MissingInformation(StrEnum):
    PRODUCT_REFERENCE = "PRODUCT_REFERENCE"
    ORDER_REFERENCE = "ORDER_REFERENCE"
    DEFECT_TYPE = "DEFECT_TYPE"
    DEFECT_LOCATION = "DEFECT_LOCATION"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    IMAGE_EVIDENCE = "IMAGE_EVIDENCE"
    ADDITIONAL_DESCRIPTION = "ADDITIONAL_DESCRIPTION"


class AnalysisRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAITING = "RETRY_WAITING"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.PARTIAL_SUCCESS, self.FAILED}


class AnalysisExecutionMode(StrEnum):
    """Immutable boundary between production workflow and observation-only runs."""

    PRIMARY = "PRIMARY"
    SHADOW = "SHADOW"


class AnalysisStageStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAITING = "RETRY_WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED}


class AnalysisAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    RETRY_WAITING = "RETRY_WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.ABANDONED}


class AnalysisPipeline(StrEnum):
    PRODUCT_DEFECT_TEXT_EXTRACTION = "product_defect_text_extraction"
    PRODUCT_DEFECT_MULTIMODAL_ANALYSIS = "product_defect_multimodal_analysis"


class AnalysisTrigger(StrEnum):
    USER_REQUEST = "USER_REQUEST"


class AnalysisStageType(StrEnum):
    TEXT_EXTRACTION = "TEXT_EXTRACTION"
    VISION_ANALYSIS = "VISION_ANALYSIS"
    EVIDENCE_ALIGNMENT = "EVIDENCE_ALIGNMENT"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    ROUTING = "ROUTING"
    REPORT_GENERATION = "REPORT_GENERATION"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


_RUN_TRANSITIONS = MappingProxyType(
    {
        AnalysisRunStatus.QUEUED: frozenset({AnalysisRunStatus.RUNNING, AnalysisRunStatus.FAILED}),
        AnalysisRunStatus.RUNNING: frozenset(
            {
                AnalysisRunStatus.SUCCEEDED,
                AnalysisRunStatus.PARTIAL_SUCCESS,
                AnalysisRunStatus.RETRY_WAITING,
                AnalysisRunStatus.FAILED,
            }
        ),
        AnalysisRunStatus.RETRY_WAITING: frozenset(
            {
                AnalysisRunStatus.RUNNING,
                AnalysisRunStatus.PARTIAL_SUCCESS,
                AnalysisRunStatus.FAILED,
            }
        ),
        AnalysisRunStatus.SUCCEEDED: frozenset(),
        AnalysisRunStatus.PARTIAL_SUCCESS: frozenset(),
        AnalysisRunStatus.FAILED: frozenset(),
    }
)
_STAGE_TRANSITIONS = MappingProxyType(
    {
        AnalysisStageStatus.QUEUED: frozenset(
            {AnalysisStageStatus.RUNNING, AnalysisStageStatus.FAILED}
        ),
        AnalysisStageStatus.RUNNING: frozenset(
            {
                AnalysisStageStatus.SUCCEEDED,
                AnalysisStageStatus.RETRY_WAITING,
                AnalysisStageStatus.FAILED,
            }
        ),
        AnalysisStageStatus.RETRY_WAITING: frozenset(
            {AnalysisStageStatus.RUNNING, AnalysisStageStatus.FAILED}
        ),
        AnalysisStageStatus.SUCCEEDED: frozenset(),
        AnalysisStageStatus.FAILED: frozenset(),
    }
)


def require_run_transition(current: AnalysisRunStatus, target: AnalysisRunStatus) -> None:
    """Reject every transition not explicitly approved by the run state machine."""

    if target not in _RUN_TRANSITIONS[current]:
        raise InvalidAnalysisTransitionError(current=current, target=target)


def require_stage_transition(current: AnalysisStageStatus, target: AnalysisStageStatus) -> None:
    """Reject every transition not explicitly approved by the stage state machine."""

    if target not in _STAGE_TRANSITIONS[current]:
        raise InvalidAnalysisTransitionError(current=current, target=target)


class GeometryType(StrEnum):
    BOUNDING_BOX = "BOUNDING_BOX"
    MASK = "MASK"


class CoordinateSystem(StrEnum):
    NORMALIZED_XYXY = "normalized_xyxy"
    NORMALIZED = "NORMALIZED"


class ImageQualityRejectionReason(StrEnum):
    BLURRED = "BLURRED"
    TOO_DARK = "TOO_DARK"
    OVEREXPOSED = "OVEREXPOSED"
    PRODUCT_NOT_VISIBLE = "PRODUCT_NOT_VISIBLE"
    DEFECT_AREA_NOT_VISIBLE = "DEFECT_AREA_NOT_VISIBLE"
    UNSUPPORTED_IMAGE = "UNSUPPORTED_IMAGE"
    OTHER = "OTHER"


class ImageUsability(StrEnum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class VisionTask(StrEnum):
    QUALITY_CHECK = "QUALITY_CHECK"
    DEFECT_DETECTION = "DEFECT_DETECTION"
    QUALITY_AND_DEFECT_DETECTION = "QUALITY_AND_DEFECT_DETECTION"
    ANY_DEFECT_CLASSIFICATION = "ANY_DEFECT_CLASSIFICATION"


class VisionImageAssessmentType(StrEnum):
    """Image-level classification tasks that do not localize or type a defect."""

    ANY_DEFECT = "ANY_DEFECT"


class VisionThresholdOperator(StrEnum):
    """Frozen comparison semantics retained beside a provider score."""

    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"


class VisionImageAssessmentOutcome(StrEnum):
    """Decision-support outcomes that deliberately contain no NORMAL state."""

    HIGH_CONFIDENCE_DEFECT_CANDIDATE = "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
    BELOW_HIGH_CONFIDENCE_THRESHOLD = "BELOW_HIGH_CONFIDENCE_THRESHOLD"


class MockProviderMode(StrEnum):
    """Deterministic scenarios exposed by Sprint 0 provider fakes."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    SCHEMA_ERROR = "schema_error"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_SOURCE_QUOTE = "invalid_source_quote"
