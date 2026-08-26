"""Offline grounded policy explanation provider contracts."""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from urllib3.response import BaseHTTPResponse

from app.adapters.llm import VLLMLLMProvider
from app.domains.product_defect_cs.prompts import GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
from app.platform.grounding import (
    CitationAllowlistViolationError,
    CitationPack,
    CitationSnapshot,
    GroundedExplanationInput,
    GroundedExplanationInvalidOutputError,
)
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import QueryStrategy

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


def _input() -> GroundedExplanationInput:
    return GroundedExplanationInput(
        case_summary="합성 문의",
        citation_pack=CitationPack(
            id="pack",
            tenant_id="tenant-a",
            case_id="case-a",
            retrieval_run_id="retrieval-a",
            retrieval_profile_hash="a" * 64,
            citations=(
                CitationSnapshot(
                    citation_id="CIT-001",
                    rank=1,
                    policy_clause_row_id="row",
                    policy_clause_id="POLICY:1.0.0:C1",
                    document_id="POLICY",
                    document_version="1.0.0",
                    title="Synthetic",
                    section_path=("Synthetic", "C1"),
                    clause_type=ClauseType.RULE,
                    text="합성 정책 근거",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    source_type="SYNTHETIC_REFERENCE",
                    source_hash="b" * 64,
                    query_strategy=QueryStrategy.RAW,
                    matched_query_ids=("Q1",),
                    retrieval_profile_hash="a" * 64,
                ),
            ),
            created_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
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
        max_output_tokens=512,
        max_output_chars=8000,
        max_input_chars=20_000,
        temperature=0,
        tls_verify=True,
        http_client=client,
        clock=iter((1.0, 1.1)).__next__,
    )


def _valid_output(citation_id: str = "CIT-001") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "summary": "현재 검색된 정책 근거를 기준으로 확인할 항목을 정리했습니다.",
        "policy_statements": [
            {
                "statement_id": "S1",
                "text": "합성 정책 근거",
                "citation_ids": [citation_id],
                "support_status": "SUPPORTED",
            }
        ],
        "unresolved_conditions": [],
    }


def test_remote_grounding_uses_strict_schema_and_citation_pack() -> None:
    client = _Client(_valid_output())
    result = _provider(client).explain_policy_grounded(
        _input(), GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
    )
    payload = json.loads(client.body)

    assert result.explanation.policy_statements[0].citation_ids == ("CIT-001",)
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["name"] == (
        "csight_grounded_policy_explanation"
    )
    assert "raw_response" not in client.body.decode()


def test_remote_grounding_rejects_unknown_citation() -> None:
    with pytest.raises(CitationAllowlistViolationError):
        _provider(_Client(_valid_output("CIT-999"))).explain_policy_grounded(
            _input(), GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
        )


def test_remote_grounding_rejects_forbidden_decision_field() -> None:
    output = _valid_output()
    output["final_decision"] = "APPROVED"
    with pytest.raises(GroundedExplanationInvalidOutputError):
        _provider(_Client(output)).explain_policy_grounded(
            _input(), GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
        )
