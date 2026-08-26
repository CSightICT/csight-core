"""Port for structured LLM extraction."""

from typing import Protocol, runtime_checkable

from app.platform.analysis import LLMAnalysisRequest, LLMCaseExtraction, ProviderMetadata
from app.platform.analysis.llm_v2 import LLMTextExtractionRequestV2, LLMTextExtractionResponseV2
from app.platform.analysis.prompts import PromptManifest
from app.platform.analysis.schemas import (
    LLMTextExtractionRequest,
    LLMTextExtractionResponse,
)
from app.platform.grounding import GroundedExplanationInput, GroundedExplanationResponse
from app.platform.query_builder import PolicyQueryBuilderInput, PolicyQueryBuilderResponse


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

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        """Return one validated, decision-free text extraction and execution metadata."""
        ...

    def extract_text_v2(
        self,
        request: LLMTextExtractionRequestV2,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponseV2:
        """Return one validated v2 extraction without deterministic backend fields."""
        ...

    def build_policy_queries(
        self,
        request: PolicyQueryBuilderInput,
        prompt: PromptManifest,
    ) -> PolicyQueryBuilderResponse:
        """Build a strict decision-free policy search plan from allowlisted facts."""
        ...

    def explain_policy_grounded(
        self,
        request: GroundedExplanationInput,
        prompt: PromptManifest,
    ) -> GroundedExplanationResponse:
        """Explain only an immutable citation pack without making a decision."""
        ...
