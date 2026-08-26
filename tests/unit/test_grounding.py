"""Citation pack and structural grounding guardrail invariants."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.adapters.llm import MockLLMProvider
from app.domains.product_defect_cs.prompts import GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1
from app.platform.grounding import (
    CitationAllowlistViolationError,
    CitationPack,
    CitationSnapshot,
    GroundedExplanationInput,
    GroundedPolicyExplanation,
    GroundedPolicyStatement,
    validate_grounded_explanation,
)
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import QueryStrategy


def _pack() -> CitationPack:
    return CitationPack(
        id="pack-1",
        tenant_id="tenant-a",
        case_id="case-1",
        retrieval_run_id="retrieval-1",
        retrieval_profile_hash="a" * 64,
        citations=(
            CitationSnapshot(
                citation_id="CIT-001",
                rank=1,
                policy_clause_row_id="row-1",
                policy_clause_id="POLICY-1:1.0.0:C1",
                document_id="POLICY-1",
                document_version="1.0.0",
                title="Synthetic policy",
                section_path=("Synthetic", "C1"),
                clause_type=ClauseType.RULE,
                text="누액이 확인된 상품은 증거와 함께 교환 검토 대상이 될 수 있습니다.",
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
    )


def test_citation_pack_hash_and_mock_generation_are_deterministic() -> None:
    pack = _pack()
    request = GroundedExplanationInput(case_summary="누액 문의", citation_pack=pack)
    provider = MockLLMProvider()

    first = provider.explain_policy_grounded(request, GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1)
    second = provider.explain_policy_grounded(request, GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1)

    assert first.explanation == second.explanation
    assert first.explanation.policy_statements[0].citation_ids == ("CIT-001",)
    assert pack.content_hash == _pack().content_hash
    assert validate_grounded_explanation(first.explanation, pack).citation_id_valid_rate == 1.0


def test_duplicate_citations_are_normalized_before_validation() -> None:
    statement = GroundedPolicyStatement(
        statement_id="S1",
        text="정책 근거",
        citation_ids=("CIT-001", "CIT-001"),
    )
    assert statement.citation_ids == ("CIT-001",)


def test_unknown_citation_fails_closed() -> None:
    explanation = GroundedPolicyExplanation(
        policy_statements=(
            GroundedPolicyStatement(
                statement_id="S1",
                text="근거 없는 정책 사실",
                citation_ids=("CIT-999",),
            ),
        ),
        unresolved_conditions=(),
    )
    with pytest.raises(CitationAllowlistViolationError):
        validate_grounded_explanation(explanation, _pack())


@pytest.mark.parametrize(
    "payload",
    [
        {
            "policy_statements": [
                {
                    "statement_id": "S1",
                    "text": "citation 없음",
                    "citation_ids": [],
                    "support_status": "SUPPORTED",
                }
            ],
            "unresolved_conditions": [],
        },
        {
            "policy_statements": [],
            "unresolved_conditions": [],
            "refund_approved": True,
        },
        {
            "summary": "정책상 환불이 승인되었습니다.",
            "policy_statements": [],
            "unresolved_conditions": [],
        },
        {
            "policy_statements": [
                {
                    "statement_id": "S1",
                    "text": "정책 근거",
                    "citation_ids": ["CIT-001"],
                    "support_status": "UNSUPPORTED",
                }
            ],
            "unresolved_conditions": [],
        },
    ],
)
def test_contract_rejects_uncited_forbidden_or_unsupported_output(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        GroundedPolicyExplanation.model_validate(payload)
