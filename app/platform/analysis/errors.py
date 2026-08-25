"""Framework-free errors raised at AI provider boundaries."""

from typing import ClassVar


class AnalysisError(Exception):
    """Base error for the technology-neutral analysis slice."""


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
