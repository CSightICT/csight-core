"""llama.cpp adapter over llama-server's OpenAI-compatible HTTP API."""

from collections.abc import Callable
from typing import Any, TypeVar

from app.adapters.llm.vllm import VLLMLLMProvider
from app.platform.analysis import LLMAnalysisRequest, LLMCaseExtraction, ProviderMetadata
from app.platform.analysis.errors import (
    AnalysisProviderError,
    LLMProviderAuthenticationError,
    LLMProviderRequestRejectedError,
    LLMProviderUnavailableError,
)
from app.platform.analysis.llm_v2 import LLMTextExtractionRequestV2, LLMTextExtractionResponseV2
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.analysis.prompts import PromptManifest
from app.platform.analysis.schemas import LLMTextExtractionRequest, LLMTextExtractionResponse
from app.platform.grounding import GroundedExplanationInput, GroundedExplanationResponse
from app.platform.query_builder import PolicyQueryBuilderInput, PolicyQueryBuilderResponse

_T = TypeVar("_T")
_PROVIDER_NAME = "llama_cpp"
_GRAMMAR_REPEAT_LIMIT_KEYS = frozenset({"maxItems", "maxLength", "minItems", "minLength"})


def _grammar_compatible_schema(value: Any) -> Any:
    """Remove bounded-repeat hints that exceed llama.cpp's grammar safety limit.

    The full Pydantic schema is still enforced on the returned payload. The
    runtime grammar only needs to constrain structure; output tokens provide a
    separate hard bound on strings and collections.
    """

    if isinstance(value, dict):
        return {
            key: _grammar_compatible_schema(item)
            for key, item in value.items()
            if key not in _GRAMMAR_REPEAT_LIMIT_KEYS
        }
    if isinstance(value, list):
        return [_grammar_compatible_schema(item) for item in value]
    return value


class LlamaCppLLMProvider(VLLMLLMProvider):
    """Call a pinned llama-server deployment without importing llama.cpp into Core.

    llama-server exposes the same chat-completions envelope used by the existing
    adapter, but its constrained-decoding contract also accepts a top-level
    ``json_schema``. Sending both forms keeps the request OpenAI-compatible while
    making schema enforcement explicit at the llama.cpp boundary.
    """

    @property
    def provider_metadata(self) -> ProviderMetadata:
        metadata = super().provider_metadata
        return metadata.model_copy(update={"provider": _PROVIDER_NAME})

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        del request
        raise LLMProviderRequestRejectedError(
            provider=_PROVIDER_NAME,
            message="the legacy extraction operation is not supported by the llama.cpp adapter",
        )

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        operation = super().extract_text
        response = self._with_llama_cpp_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _llama_cpp_metadata(response.metadata)})

    def extract_text_v2(
        self,
        request: LLMTextExtractionRequestV2,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponseV2:
        operation = super().extract_text_v2
        response = self._with_llama_cpp_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _llama_cpp_metadata(response.metadata)})

    def build_policy_queries(
        self,
        request: PolicyQueryBuilderInput,
        prompt: PromptManifest,
    ) -> PolicyQueryBuilderResponse:
        operation = super().build_policy_queries
        response = self._with_llama_cpp_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _llama_cpp_metadata(response.metadata)})

    def explain_policy_grounded(
        self,
        request: GroundedExplanationInput,
        prompt: PromptManifest,
    ) -> GroundedExplanationResponse:
        operation = super().explain_policy_grounded
        response = self._with_llama_cpp_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _llama_cpp_metadata(response.metadata)})

    def _request_payload(
        self,
        *,
        system_message: str,
        user_message: str,
        schema: dict[str, Any],
        schema_name: str = "csight_text_extraction",
    ) -> dict[str, object]:
        grammar_schema = _grammar_compatible_schema(schema)
        payload = super()._request_payload(
            system_message=system_message,
            user_message=user_message,
            schema=grammar_schema,
            schema_name=schema_name,
        )
        payload["json_schema"] = grammar_schema
        payload["reasoning_effort"] = "none"
        payload["chat_template_kwargs"] = {
            "enable_thinking": False,
            "preserve_thinking": False,
        }
        return payload

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise LLMProviderAuthenticationError(
                provider=_PROVIDER_NAME,
                message="the llama.cpp service rejected its configured credentials",
            )
        if status == 429 or status >= 500:
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message=f"the llama.cpp service is unavailable (HTTP {status})",
            )
        raise LLMProviderRequestRejectedError(
            provider=_PROVIDER_NAME,
            message=f"the llama.cpp service rejected the request (HTTP {status})",
        )

    @staticmethod
    def _with_llama_cpp_errors(operation: Callable[[], _T]) -> _T:
        try:
            return operation()
        except AnalysisProviderError as error:
            message = error.message.replace("vLLM", "llama.cpp")
            raise type(error)(provider=_PROVIDER_NAME, message=message) from None


def _llama_cpp_metadata(metadata: ProviderExecutionMetadata) -> ProviderExecutionMetadata:
    return metadata.model_copy(update={"provider_name": _PROVIDER_NAME})


__all__ = ["LlamaCppLLMProvider"]
