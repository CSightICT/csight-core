"""Port for structured LLM extraction."""

from typing import Protocol, runtime_checkable

from app.platform.analysis import LLMAnalysisRequest, LLMCaseExtraction, ProviderMetadata


@runtime_checkable
class LLMProvider(Protocol):
    """Technology-neutral contract implemented by LLM adapters."""

    @property
    def provider_metadata(self) -> ProviderMetadata:
        """Return the configured provider and model deployment identity."""
        ...

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        """Extract claims from customer text without making a business decision."""
        ...
