"""Offline policy Query Builder provider contracts."""

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest
from urllib3.response import BaseHTTPResponse

from app.adapters.llm import MockLLMProvider, VLLMLLMProvider
from app.domains.product_defect_cs.prompts import POLICY_QUERY_BUILDER_PROMPT_V1_1
from app.platform.analysis.enums import ExtractionIssueType, MockProviderMode
from app.platform.analysis.errors import (
    LLMProviderRequestRejectedError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMTextExtractionResultV2,
)
from app.platform.query_builder import (
    PolicyQueryBuilderInput,
    PolicyQueryBuilderInvalidOutputError,
    TrustedCaseMetadata,
)

pytestmark = pytest.mark.contract


class _Response:
    status = 200
    headers: Mapping[str, str] = {}

    def __init__(self, content: dict[str, object]) -> None:
        self.body = json.dumps(
            {
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            }
        ).encode()

    def read(self, amt: int | None = None, **_kwargs: object) -> bytes:
        return self.body if amt is None else self.body[:amt]

    def release_conn(self) -> None:
        return None


class _Client:
    def __init__(self, content: dict[str, object]) -> None:
        self.response = _Response(content)
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
        return cast(BaseHTTPResponse, self.response)


def _input() -> PolicyQueryBuilderInput:
    return PolicyQueryBuilderInput(
        extraction=LLMTextExtractionResultV2(
            issue_types=(ExtractionIssueType.LEAKAGE,), summary="누액"
        ),
        completeness=CompletenessResult(
            system_missing_information=(),
            action_consistency=ActionConsistency.BOTH_UNSPECIFIED,
        ),
        trusted_metadata=TrustedCaseMetadata(product_category="GENERAL"),
    )


def _provider(client: _Client) -> VLLMLLMProvider:
    return VLLMLLMProvider(
        base_url="https://vllm.invalid",
        api_key=None,
        model_id="Qwen-test",
        model_version="test",
        model_revision="revision",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        max_output_tokens=256,
        max_output_chars=4000,
        max_input_chars=4000,
        temperature=0,
        tls_verify=True,
        http_client=client,
        clock=iter((1.0, 1.1)).__next__,
    )


def test_remote_query_builder_uses_strict_schema_and_no_customer_message() -> None:
    client = _Client(
        {
            "schema_version": "1.0",
            "queries": [{"query_id": "Q1", "purpose": "PRIMARY_POLICY", "text": "누액 기준"}],
            "filter_hints": {"defect_types": ["LEAKAGE"]},
            "unresolved_terms": [],
        }
    )
    response = _provider(client).build_policy_queries(_input(), POLICY_QUERY_BUILDER_PROMPT_V1_1)
    payload = json.loads(client.body)

    assert response.plan.queries[0].text == "누액 기준"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert "customer_message" not in client.body.decode()


@pytest.mark.parametrize(
    "content",
    [
        {},
        {"schema_version": "1.0", "queries": [], "filter_hints": {}, "unresolved_terms": []},
        {
            "schema_version": "1.0",
            "queries": [{"query_id": "Q1", "purpose": "UNKNOWN", "text": "x"}],
            "filter_hints": {},
            "unresolved_terms": [],
        },
        {
            "schema_version": "1.0",
            "queries": [
                {"query_id": "Q1", "purpose": "PRIMARY_POLICY", "text": "same"},
                {"query_id": "Q2", "purpose": "PROCEDURE", "text": "same"},
            ],
            "filter_hints": {},
            "unresolved_terms": [],
        },
        {
            "schema_version": "1.0",
            "queries": [{"query_id": "Q1", "purpose": "PRIMARY_POLICY", "text": "valid"}],
            "filter_hints": {},
            "unresolved_terms": [],
            "tenant_id": "forbidden",
        },
    ],
)
def test_remote_query_builder_rejects_invalid_structured_output(content: dict[str, object]) -> None:
    with pytest.raises(PolicyQueryBuilderInvalidOutputError):
        _provider(_Client(content)).build_policy_queries(_input(), POLICY_QUERY_BUILDER_PROMPT_V1_1)


@pytest.mark.parametrize(
    ("mode", "error"),
    [
        (MockProviderMode.TIMEOUT, LLMProviderTimeoutError),
        (MockProviderMode.TRANSIENT_ERROR, LLMProviderUnavailableError),
        (MockProviderMode.PERMANENT_ERROR, LLMProviderRequestRejectedError),
    ],
)
def test_mock_query_builder_normalizes_provider_failures(
    mode: MockProviderMode, error: type[Exception]
) -> None:
    with pytest.raises(error):
        MockLLMProvider(mode=mode).build_policy_queries(_input(), POLICY_QUERY_BUILDER_PROMPT_V1_1)
