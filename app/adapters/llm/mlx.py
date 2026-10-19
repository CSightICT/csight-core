"""Local MLX adapter over the runtime's OpenAI-compatible HTTP contract."""

from collections.abc import Callable
from copy import deepcopy
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
from app.platform.policy_reference import POLICY_TYPES
from app.platform.policy_retrieval import PRODUCT_CATEGORIES
from app.platform.query_builder import PolicyQueryBuilderInput, PolicyQueryBuilderResponse

_T = TypeVar("_T")
_PROVIDER_NAME = "mlx"
_SERVED_MODEL_NAME = "csight-qwen3.5-9b-local-poc"


class MLXLLMProvider(VLLMLLMProvider):
    """Use strict OpenAI-compatible generation while preserving MLX identity.

    The local runtime is deliberately accessed through HTTP. No MLX package is
    imported into the application process, and the existing technology-neutral
    ``LLMProvider`` port remains unchanged.
    """

    # MLX-VLM may return this provider extension despite thinking being disabled.
    # The field is never propagated; only the separately typed content is parsed.
    _redact_reasoning_content = True

    @property
    def provider_metadata(self) -> ProviderMetadata:
        metadata = super().provider_metadata
        return metadata.model_copy(update={"provider": _PROVIDER_NAME, "name": _SERVED_MODEL_NAME})

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        operation = super().extract_case
        return self._with_mlx_errors(lambda: operation(request))

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        operation = super().extract_text
        response = self._with_mlx_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _mlx_metadata(response.metadata)})

    def extract_text_v2(
        self,
        request: LLMTextExtractionRequestV2,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponseV2:
        operation = super().extract_text_v2
        response = self._with_mlx_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _mlx_metadata(response.metadata)})

    def build_policy_queries(
        self,
        request: PolicyQueryBuilderInput,
        prompt: PromptManifest,
    ) -> PolicyQueryBuilderResponse:
        operation = super().build_policy_queries
        response = self._with_mlx_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _mlx_metadata(response.metadata)})

    def explain_policy_grounded(
        self,
        request: GroundedExplanationInput,
        prompt: PromptManifest,
    ) -> GroundedExplanationResponse:
        operation = super().explain_policy_grounded
        response = self._with_mlx_errors(lambda: operation(request, prompt))
        return response.model_copy(update={"metadata": _mlx_metadata(response.metadata)})

    def _request_payload(
        self,
        *,
        system_message: str,
        user_message: str,
        schema: dict[str, Any],
        schema_name: str = "csight_text_extraction",
    ) -> dict[str, object]:
        payload = super()._request_payload(
            system_message=system_message,
            user_message=user_message,
            schema=_mlx_constrained_schema(schema, schema_name=schema_name),
            schema_name=schema_name,
        )
        # MLX-VLM exposes this as a top-level OpenAI extension. The inherited
        # chat-template flags remain for parity with vLLM and defense in depth.
        payload["enable_thinking"] = False
        return payload

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise LLMProviderAuthenticationError(
                provider=_PROVIDER_NAME,
                message="the local MLX service rejected its configured credentials",
            )
        if status == 429 or status >= 500:
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message=f"the local MLX service is unavailable (HTTP {status})",
            )
        raise LLMProviderRequestRejectedError(
            provider=_PROVIDER_NAME,
            message=f"the local MLX service rejected the request (HTTP {status})",
        )

    @staticmethod
    def _with_mlx_errors(operation: Callable[[], _T]) -> _T:
        try:
            return operation()
        except AnalysisProviderError as error:
            raise type(error)(provider=_PROVIDER_NAME, message=error.message) from None


def _mlx_metadata(metadata: ProviderExecutionMetadata) -> ProviderExecutionMetadata:
    return metadata.model_copy(
        update={"provider_name": _PROVIDER_NAME, "model_name": _SERVED_MODEL_NAME}
    )


def _require_all_object_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Make omitted defaulted fields impossible during constrained decoding.

    Pydantic intentionally omits defaulted fields from JSON Schema ``required``.
    MLX-VLM's grammar then permits the model to leave out fields whose values are
    needed by cross-field validators. Requiring every declared output property is
    stricter than the shared contract and avoids any post-generation repair.
    """

    normalized = deepcopy(schema)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(normalized)
    return normalized


def _mlx_constrained_schema(schema: dict[str, Any], *, schema_name: str) -> dict[str, Any]:
    normalized = _require_all_object_properties(schema)
    if schema_name == "csight_grounded_policy_explanation":
        root_properties = normalized.get("properties")
        if isinstance(root_properties, dict):
            policy_statements = root_properties.get("policy_statements")
            if isinstance(policy_statements, dict):
                policy_statements["minItems"] = 1
        return normalized
    if schema_name != "csight_policy_query_plan":
        return normalized

    definitions = normalized.get("$defs")
    if not isinstance(definitions, dict):
        return normalized
    hints = definitions.get("QueryFilterHints")
    if not isinstance(hints, dict):
        return normalized
    properties = hints.get("properties")
    if not isinstance(properties, dict):
        return normalized
    for field_name, allowlist in (
        ("policy_types", sorted(POLICY_TYPES)),
        ("product_categories", sorted(PRODUCT_CATEGORIES)),
    ):
        field_schema = properties.get(field_name)
        if not isinstance(field_schema, dict):
            continue
        items = field_schema.get("items")
        if isinstance(items, dict):
            items["enum"] = allowlist
        field_schema["maxItems"] = 1
    for field_name in ("defect_types", "clause_types"):
        field_schema = properties.get(field_name)
        if isinstance(field_schema, dict):
            field_schema["maxItems"] = 1
    query_definition = definitions.get("PolicyQuery")
    if isinstance(query_definition, dict):
        query_properties = query_definition.get("properties")
        if isinstance(query_properties, dict):
            query_properties["query_id"] = {"type": "string", "enum": ["Q1"]}
            query_properties["purpose"] = {
                "type": "string",
                "enum": ["PRIMARY_POLICY"],
            }
            query_text = query_properties.get("text")
            if isinstance(query_text, dict):
                query_text["maxLength"] = 120
    root_properties = normalized.get("properties")
    if isinstance(root_properties, dict):
        queries = root_properties.get("queries")
        if isinstance(queries, dict):
            queries["maxItems"] = 1
        unresolved_terms = root_properties.get("unresolved_terms")
        if isinstance(unresolved_terms, dict):
            unresolved_terms["maxItems"] = 0
    return normalized
