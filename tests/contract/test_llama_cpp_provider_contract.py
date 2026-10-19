"""Offline transport and failure contracts for the llama-server adapter."""

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest
from urllib3 import Timeout
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError
from urllib3.response import BaseHTTPResponse

from app.adapters.llm import LlamaCppLLMProvider
from app.platform.analysis.enums import CustomerRequest
from app.platform.analysis.errors import (
    LLMExtraFieldError,
    LLMInvalidEnumValueError,
    LLMInvalidStructuredOutputError,
    LLMMissingRequiredFieldError,
    LLMProviderRequestRejectedError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMStructuredConstraintError,
    LLMStructuredJSONInvalidError,
    LLMStructuredOutputTruncatedError,
)
from app.platform.analysis.llm_v2 import LLMTextExtractionRequestV2
from app.platform.analysis.prompts import PromptManifest
from app.platform.analysis.schemas import LLMTextExtractionRequest, LLMTextExtractionResult
from app.ports.llm import LLMProvider

pytestmark = pytest.mark.contract


class _Response:
    def __init__(self, *, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.headers: Mapping[str, str] = {"x-request-id": "llama-request-1"}

    def read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
    ) -> bytes:
        del decode_content, cache_content
        return self.body if amt is None else self.body[:amt]

    def release_conn(self) -> None:
        return None


class _Client:
    def __init__(
        self,
        response: _Response | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

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
        del fields, json
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": body,
                "headers": dict(headers or {}),
                "urlopen_kw": urlopen_kw,
            }
        )
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("a response is required")
        return cast(BaseHTTPResponse, self.response)


def _prompt() -> PromptManifest:
    return PromptManifest.create(
        name="synthetic-text-extraction",
        version="llama-cpp-contract",
        input_schema_version="1.0",
        output_schema_version="1.0",
        system_template="Extract facts only and return the required JSON object.",
        user_template="Allowlisted input JSON:\n{input_json}",
    )


def _request() -> LLMTextExtractionRequest:
    return LLMTextExtractionRequest(
        customer_message="Synthetic package leaks at the bottom; please exchange it.",
        order_ref="SYNTHETIC-ORDER-1",
        product_ref="SYNTHETIC-PRODUCT-1",
        requested_action=CustomerRequest.EXCHANGE,
    )


def _completion(
    *,
    content: str | None = None,
    reasoning_content: object | None = None,
    finish_reason: str = "stop",
) -> bytes:
    if content is None:
        content = json.dumps(
            {
                "schema_version": "1.0",
                "language": "en",
                "issue_types": ["LEAKAGE"],
                "claims": [
                    {
                        "type": "LEAKAGE",
                        "location": "BOTTOM",
                        "description": "The package is reported to leak from the bottom.",
                        "source_quote": "leaks at the bottom",
                    }
                ],
                "requested_action": "EXCHANGE",
                "missing_information": [],
                "summary": "The customer reports a leak and requests an exchange.",
            },
            separators=(",", ":"),
        )
    message: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning_content is not None:
        message["reasoning_content"] = reasoning_content
    return json.dumps(
        {
            "id": "chatcmpl-llama-contract",
            "model": "csight-qwen3.8-27b-gguf",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": message,
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30},
        },
        separators=(",", ":"),
    ).encode()


def _provider(client: _Client) -> LlamaCppLLMProvider:
    clock = iter((10.0, 10.2))
    return LlamaCppLLMProvider(
        base_url="https://llama.internal.test/v1",
        api_key="contract-private-key",
        model_id="csight-qwen3.8-27b-gguf",
        model_version="Qwen3.8-27B-GGUF-Q4",
        model_revision="a" * 40,
        connect_timeout_seconds=3.0,
        read_timeout_seconds=120.0,
        max_output_tokens=1024,
        max_output_chars=20_000,
        max_input_chars=20_000,
        temperature=0.0,
        tls_verify=True,
        http_client=client,
        clock=lambda: next(clock),
    )


def _request_v2() -> LLMTextExtractionRequestV2:
    return LLMTextExtractionRequestV2(
        customer_message="합성 용기가 깨져 교환해주세요.",
        order_ref="SYNTHETIC-ORDER-1",
        product_ref="SYNTHETIC-PRODUCT-1",
    )


def _prompt_v2() -> PromptManifest:
    return PromptManifest.create(
        name="synthetic-text-extraction-v2",
        version="llama-cpp-contract-v2",
        input_schema_version="2.0",
        output_schema_version="2.0",
        system_template="Return the required JSON object only.",
        user_template="Allowlisted input JSON:\n{input_json}",
    )


def test_llama_cpp_uses_alias_schema_constraints_and_disables_thinking() -> None:
    client = _Client(_Response(body=_completion()))
    provider = _provider(client)

    assert isinstance(provider, LLMProvider)
    response = provider.extract_text(_request(), _prompt())

    assert response.metadata.provider_name == "llama_cpp"
    assert response.metadata.model_name == "csight-qwen3.8-27b-gguf"
    assert provider.provider_metadata.provider == "llama_cpp"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://llama.internal.test/v1/chat/completions"
    headers = cast(dict[str, str], call["headers"])
    assert headers["Authorization"] == "Bearer contract-private-key"
    options = cast(dict[str, object], call["urlopen_kw"])
    timeout = cast(Timeout, options["timeout"])
    assert timeout.connect_timeout == 3.0
    assert timeout.read_timeout == 120.0

    payload = json.loads(cast(bytes, call["body"]))
    full_schema = LLMTextExtractionResult.model_json_schema()
    grammar_schema = payload["json_schema"]
    assert grammar_schema != full_schema

    def repeat_keywords(value: object) -> set[str]:
        if isinstance(value, dict):
            return {
                key for key in value if key in {"maxItems", "maxLength", "minItems", "minLength"}
            } | set().union(*(repeat_keywords(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(repeat_keywords(item) for item in value))
        return set()

    assert repeat_keywords(grammar_schema) == set()
    assert repeat_keywords(full_schema) == {"maxItems", "maxLength", "minItems", "minLength"}
    assert payload["model"] == "csight-qwen3.8-27b-gguf"
    assert payload["reasoning_effort"] == "none"
    assert payload["chat_template_kwargs"] == {
        "enable_thinking": False,
        "preserve_thinking": False,
    }
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "csight_text_extraction",
            "strict": True,
            "schema": grammar_schema,
        },
    }


@pytest.mark.parametrize("status", [429, 500, 503])
def test_llama_cpp_retryable_http_failures_are_normalized(status: int) -> None:
    with pytest.raises(LLMProviderUnavailableError) as caught:
        _provider(_Client(_Response(body=b"{}", status=status))).extract_text(_request(), _prompt())

    assert caught.value.provider == "llama_cpp"
    assert caught.value.retryable is True


def test_llama_cpp_timeout_is_retryable() -> None:
    with pytest.raises(LLMProviderTimeoutError) as caught:
        _provider(_Client(error=Urllib3TimeoutError("synthetic timeout"))).extract_text(
            _request(), _prompt()
        )

    assert caught.value.provider == "llama_cpp"
    assert caught.value.retryable is True


def test_llama_cpp_request_rejection_and_invalid_schema_are_permanent() -> None:
    with pytest.raises(LLMProviderRequestRejectedError) as rejected:
        _provider(_Client(_Response(body=b"{}", status=400))).extract_text(_request(), _prompt())
    assert rejected.value.provider == "llama_cpp"
    assert rejected.value.retryable is False

    with pytest.raises(LLMInvalidStructuredOutputError) as invalid:
        _provider(_Client(_Response(body=_completion(content="not-json")))).extract_text(
            _request(), _prompt()
        )
    assert invalid.value.provider == "llama_cpp"
    assert invalid.value.retryable is False
    assert "llama.cpp" in invalid.value.message
    assert "vLLM" not in invalid.value.message


@pytest.mark.parametrize(
    ("content", "finish_reason", "expected_error"),
    (
        ("not-json", "stop", LLMStructuredJSONInvalidError),
        ('{"schema_version":"2.0"}', "stop", LLMMissingRequiredFieldError),
        (
            '{"schema_version":"2.0","issue_types":["NOT_REAL"],"summary":"합성"}',
            "stop",
            LLMInvalidEnumValueError,
        ),
        (
            '{"schema_version":"2.0","summary":"합성","unexpected":true}',
            "stop",
            LLMExtraFieldError,
        ),
        (
            '{"schema_version":"2.0","issue_types":["BREAKAGE","BREAKAGE"],"summary":"합성"}',
            "stop",
            LLMStructuredConstraintError,
        ),
        ('{"schema_version":"2.0"}', "length", LLMStructuredOutputTruncatedError),
    ),
)
def test_llama_cpp_extraction_v2_exposes_privacy_safe_failure_taxonomy(
    content: str,
    finish_reason: str,
    expected_error: type[LLMInvalidStructuredOutputError],
) -> None:
    with pytest.raises(expected_error) as caught:
        _provider(
            _Client(_Response(body=_completion(content=content, finish_reason=finish_reason)))
        ).extract_text_v2(_request_v2(), _prompt_v2())

    assert caught.value.provider == "llama_cpp"
    assert caught.value.retryable is False
    assert "customer_message" not in caught.value.message
    assert "합성 용기" not in caught.value.message


@pytest.mark.parametrize("reasoning_content", ("", "hidden chain", {"step": "hidden"}))
def test_llama_cpp_rejects_reasoning_content_even_with_valid_json(
    reasoning_content: object,
) -> None:
    with pytest.raises(LLMInvalidStructuredOutputError, match="reasoning_content"):
        _provider(
            _Client(_Response(body=_completion(reasoning_content=reasoning_content)))
        ).extract_text(_request(), _prompt())
