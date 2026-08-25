"""Public, technology-neutral AI analysis contracts."""

from app.platform.analysis.enums import (
    CoordinateSystem,
    CustomerRequest,
    DefectLocation,
    DefectType,
    GeometryType,
    MockProviderMode,
    VisionTask,
)
from app.platform.analysis.errors import (
    AnalysisError,
    AnalysisProviderError,
    ProviderFailureError,
    ProviderSchemaError,
    ProviderTimeoutError,
)
from app.platform.analysis.schemas import (
    SCHEMA_VERSION,
    AnalysisVersionReferences,
    BoundingBox,
    DetectionFinding,
    ImageQualityResult,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    LLMClaim,
    ProviderMetadata,
    VisionAnalysisRequest,
    VisionAnalysisResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "AnalysisError",
    "AnalysisProviderError",
    "AnalysisVersionReferences",
    "BoundingBox",
    "CoordinateSystem",
    "CustomerRequest",
    "DefectLocation",
    "DefectType",
    "DetectionFinding",
    "GeometryType",
    "ImageQualityResult",
    "LLMAnalysisRequest",
    "LLMCaseExtraction",
    "LLMClaim",
    "MockProviderMode",
    "ProviderFailureError",
    "ProviderMetadata",
    "ProviderSchemaError",
    "ProviderTimeoutError",
    "VisionAnalysisRequest",
    "VisionAnalysisResult",
    "VisionTask",
]
