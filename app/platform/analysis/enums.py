"""Technology-agnostic enums shared by AI analysis contracts."""

from enum import StrEnum


class DefectType(StrEnum):
    """Normalized product-defect taxonomy used at the provider boundary."""

    LEAKAGE = "LEAKAGE"
    CONTAINER_DAMAGE = "CONTAINER_DAMAGE"
    DENT = "DENT"
    CRACK = "CRACK"
    SCRATCH = "SCRATCH"
    DISCOLORATION = "DISCOLORATION"
    MISSING_PART = "MISSING_PART"
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


class GeometryType(StrEnum):
    BOUNDING_BOX = "BOUNDING_BOX"


class CoordinateSystem(StrEnum):
    NORMALIZED = "NORMALIZED"


class VisionTask(StrEnum):
    QUALITY_CHECK = "QUALITY_CHECK"
    DEFECT_DETECTION = "DEFECT_DETECTION"
    QUALITY_AND_DEFECT_DETECTION = "QUALITY_AND_DEFECT_DETECTION"


class MockProviderMode(StrEnum):
    """Deterministic scenarios exposed by Sprint 0 provider fakes."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    SCHEMA_ERROR = "schema_error"
