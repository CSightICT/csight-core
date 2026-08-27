"""Offline contracts for the Local MLX OpenAI-compatible adapter."""

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError
from urllib3.response import BaseHTTPResponse

from app.adapters.llm import MLXLLMProvider
from app.domains.product_defect_cs.prompts import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.platform.analysis.enums import CustomerRequest
from app.platform.analysis.errors import (
    LLMInvalidStructuredOutputError,
    LLMProviderTimeoutError,
)
from app.platform.analysis.llm_v2 import LLMTextExtractionRequestV2
from app.platform.query_builder import PolicyQueryPlan
from app.ports.llm import LLMProvider

pytestmark = pytest.mark.contract


class _Response:
    status = 200
    headers: Mapping[str, str] = {"x-request-id": "mlx-request-1"}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, amt: int | None = None, **_kwargs: object) -> bytes:
        return self.body if amt is None else self.body[:amt]

    def release_conn(self) -> None:
        return None


class _Client:
    def __init__(self, body: bytes | None = None, error: Exception | None = None) -> None:
        self.response = _Response(body or b"")
        self.error = error
        self.body = b""

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        fields: object | None = None,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        **urlopen_kw: Any,
    ) -> BaseHTTPResponse:
        del method, url, fields, headers, json, urlopen_kw
        self.body = cast(bytes, body)
        if self.error is not None:
            raise self.error
        return cast(BaseHTTPResponse, self.response)


def _body(*, content: str | None = None, reasoning: str | None = None) -> bytes:
    if content is None:
        content = json.dumps(
            {
                "schema_version": "2.0",
                "language": "ko",
                "issue_types": [],
                "claims": [],
                "requested_actions": [],
                "text_ambiguities": ["DESCRIPTION_TOO_VAGUE"],
                "summary": "명시된 결함을 확인하지 못했습니다.",
            }
        )
    return json.dumps(
        {
            "id": "chatcmpl-local",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "reasoning_content": reasoning,
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12},
        }
    ).encode()


def _provider(client: _Client) -> MLXLLMProvider:
    return MLXLLMProvider(
        base_url="http://host.docker.internal:8080/v1",
        api_key=None,
        model_id="local-pinned-snapshot",
        model_version="Qwen3.5-9B-MLX-4bit",
        model_revision="938d8919941c6e7efd3c7150eff7fe9d12afa631",
        connect_timeout_seconds=10,
        read_timeout_seconds=180,
        max_output_tokens=512,
        max_output_chars=20_000,
        max_input_chars=20_000,
        temperature=0,
        tls_verify=False,
        http_client=client,
        clock=iter((1.0, 1.1)).__next__,
    )


def _request() -> LLMTextExtractionRequestV2:
    return LLMTextExtractionRequestV2(
        customer_message="상태를 확인해 주세요.",
        declared_requested_action=CustomerRequest.UNSPECIFIED,
    )


def test_mlx_metadata_payload_and_reasoning_redaction() -> None:
    client = _Client(_body(reasoning="synthetic hidden reasoning"))
    provider = _provider(client)

    assert isinstance(provider, LLMProvider)
    assert provider.provider_metadata.provider == "mlx"
    assert provider.provider_metadata.name == "csight-qwen3.5-9b-local-poc"
    response = provider.extract_text_v2(_request(), PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2)
    payload = json.loads(client.body)

    assert response.metadata.provider_name == "mlx"
    assert response.metadata.model_name == "csight-qwen3.5-9b-local-poc"
    assert response.metadata.model_version == "Qwen3.5-9B-MLX-4bit"
    assert response.metadata.model_revision == "938d8919941c6e7efd3c7150eff7fe9d12afa631"
    assert payload["enable_thinking"] is False
    assert payload["chat_template_kwargs"] == {
        "enable_thinking": False,
        "preserve_thinking": False,
    }
    assert payload["response_format"]["type"] == "json_schema"
    response_schema = payload["response_format"]["json_schema"]["schema"]
    assert set(response_schema["required"]) == set(response_schema["properties"])
    claim_schema = response_schema["$defs"]["LLMTextClaimV2"]
    assert set(claim_schema["required"]) == set(claim_schema["properties"])
    assert "synthetic hidden reasoning" not in response.model_dump_json()


def test_mlx_invalid_json_is_not_repaired_and_keeps_provider_identity() -> None:
    with pytest.raises(LLMInvalidStructuredOutputError) as caught:
        _provider(_Client(_body(content="not-json"))).extract_text_v2(
            _request(), PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
        )
    assert caught.value.provider == "mlx"


def test_mlx_timeout_is_retryable_and_keeps_provider_identity() -> None:
    with pytest.raises(LLMProviderTimeoutError) as caught:
        _provider(_Client(error=Urllib3TimeoutError("synthetic timeout"))).extract_text_v2(
            _request(), PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
        )
    assert caught.value.provider == "mlx"
    assert caught.value.retryable is True


def test_mlx_query_schema_adds_runtime_enforced_string_allowlists() -> None:
    provider = _provider(_Client(_body()))
    payload = provider._request_payload(  # pyright: ignore[reportPrivateUsage]
        system_message="system",
        user_message="user",
        schema=PolicyQueryPlan.model_json_schema(),
        schema_name="csight_policy_query_plan",
    )
    response_format = cast(dict[str, Any], payload["response_format"])
    json_schema = cast(dict[str, Any], response_format["json_schema"])
    schema = cast(dict[str, Any], json_schema["schema"])
    definitions = cast(dict[str, Any], schema["$defs"])
    query_hints = cast(dict[str, Any], definitions["QueryFilterHints"])
    hints = cast(dict[str, Any], query_hints["properties"])
    policy_types = cast(dict[str, Any], hints["policy_types"])
    policy_items = cast(dict[str, Any], policy_types["items"])
    product_categories = cast(dict[str, Any], hints["product_categories"])
    product_items = cast(dict[str, Any], product_categories["items"])
    assert "RETURN_EXCHANGE" in cast(list[str], policy_items["enum"])
    assert "GENERAL" in cast(list[str], product_items["enum"])
    policy_query = cast(dict[str, Any], definitions["PolicyQuery"])
    query_properties = cast(dict[str, Any], policy_query["properties"])
    assert query_properties["query_id"]["enum"] == ["Q1"]
    assert query_properties["purpose"]["enum"] == ["PRIMARY_POLICY"]
    assert query_properties["text"]["maxLength"] == 120
    root_properties = cast(dict[str, Any], schema["properties"])
    assert root_properties["queries"]["maxItems"] == 1
    assert root_properties["unresolved_terms"]["maxItems"] == 0
    assert all(cast(dict[str, Any], hints[name])["maxItems"] == 1 for name in hints)
