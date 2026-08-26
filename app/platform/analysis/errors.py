"""Framework-free errors raised by analysis contracts and provider boundaries."""

from typing import ClassVar


class AnalysisError(Exception):
    """Base error for the technology-neutral analysis slice."""


class InvalidAnalysisTransitionError(AnalysisError):
    """A run or stage attempted a transition outside its explicit state machine."""

    code = "INVALID_ANALYSIS_STATE_TRANSITION"

    def __init__(self, *, current: object, target: object) -> None:
        self.current = str(current)
        self.target = str(target)
        super().__init__(f"{self.code}: {self.current} -> {self.target}")


class AnalysisProviderError(AnalysisError):
    """Base class for normalized LLM and Vision provider failures."""

    code: ClassVar[str] = "ANALYSIS_PROVIDER_ERROR"
    retryable: ClassVar[bool] = False

    def __init__(self, *, provider: str, message: str) -> None:
        self.provider = provider
        self.message = message
        super().__init__(f"{self.code}: {provider}: {message}")


class ProviderTimeoutError(AnalysisProviderError):
    """The provider did not respond within its configured deadline."""

    code = "PROVIDER_TIMEOUT"
    retryable = True


class ProviderFailureError(AnalysisProviderError):
    """The provider returned an operational failure."""

    code = "PROVIDER_FAILURE"
    retryable = True


class ProviderSchemaError(AnalysisProviderError):
    """The provider response could not be normalized to the common contract."""

    code = "PROVIDER_SCHEMA_ERROR"
    retryable = False


class LLMProviderTimeoutError(ProviderTimeoutError):
    code = "LLM_PROVIDER_TIMEOUT"


class LLMProviderUnavailableError(ProviderFailureError):
    code = "LLM_PROVIDER_UNAVAILABLE"


class LLMProviderAuthenticationError(AnalysisProviderError):
    code = "LLM_PROVIDER_AUTHENTICATION_FAILED"


class LLMProviderRequestRejectedError(AnalysisProviderError):
    code = "LLM_PROVIDER_REQUEST_REJECTED"


class LLMInvalidStructuredOutputError(ProviderSchemaError):
    code = "LLM_INVALID_STRUCTURED_OUTPUT"


class LLMSourceQuoteMismatchError(ProviderSchemaError):
    code = "LLM_SOURCE_QUOTE_MISMATCH"


class AnalysisRunNotFoundError(AnalysisError):
    code = "ANALYSIS_RUN_NOT_FOUND"


class AnalysisPipelineNotSupportedError(AnalysisError):
    code = "ANALYSIS_PIPELINE_NOT_SUPPORTED"


class AnalysisAlreadyTerminalError(AnalysisError):
    code = "ANALYSIS_ALREADY_TERMINAL"


class AnalysisMaxRetriesExceededError(AnalysisError):
    code = "ANALYSIS_MAX_RETRIES_EXCEEDED"


class OutboxDispatchFailedError(AnalysisError):
    code = "OUTBOX_DISPATCH_FAILED"


class ImageEvidenceRequiredError(AnalysisError):
    code = "IMAGE_EVIDENCE_REQUIRED"


class VisionProviderTimeoutError(ProviderTimeoutError):
    code = "VISION_PROVIDER_TIMEOUT"


class VisionProviderUnavailableError(ProviderFailureError):
    code = "VISION_PROVIDER_UNAVAILABLE"


class VisionProviderAuthenticationError(AnalysisProviderError):
    code = "VISION_PROVIDER_AUTHENTICATION_FAILED"


class VisionProviderRequestRejectedError(AnalysisProviderError):
    code = "VISION_PROVIDER_REQUEST_REJECTED"


class VisionInvalidStructuredOutputError(ProviderSchemaError):
    code = "VISION_INVALID_STRUCTURED_OUTPUT"
