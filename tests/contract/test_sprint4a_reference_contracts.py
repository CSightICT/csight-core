"""Public strict-schema contracts introduced by Sprint 4A."""

import pytest
from pydantic import ValidationError

from app.domains.product_defect_cs import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
)
from app.platform.analysis import (
    ExtractedActionV2,
    GroundedPolicyExplanation,
    LLMTextExtractionResultV2,
    PolicyQueryBuilderResult,
    RequestedActionItemV2,
)
from app.platform.analysis.errors import LLMSourceQuoteMismatchError

pytestmark = pytest.mark.contract


def test_extraction_v1_manifest_is_preserved_beside_v2() -> None:
    assert PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT.version == "1.0.1"
    assert PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT.output_schema_version == "1.0"
    assert PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.version == "2.0.0"
    assert PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2.output_schema_version == "2.0"


def test_extraction_v2_rejects_extra_fields_and_invalid_action_quote() -> None:
    with pytest.raises(ValidationError):
        LLMTextExtractionResultV2.model_validate(
            {
                "schema_version": "2.0",
                "language": "ko",
                "issue_types": [],
                "claims": [],
                "requested_actions": [],
                "text_ambiguities": [],
                "summary": "요청 없음",
                "decision": "APPROVE",
            }
        )

    result = LLMTextExtractionResultV2(
        requested_actions=(
            RequestedActionItemV2(action=ExtractedActionV2.EXCHANGE, source_quote="교환"),
        ),
        summary="교환 요청",
    )
    with pytest.raises(LLMSourceQuoteMismatchError):
        result.require_exact_source_quotes(customer_message="환불해주세요", provider="contract")


def test_extraction_v2_preserves_multiple_actions_and_represents_no_action_as_empty() -> None:
    multiple = LLMTextExtractionResultV2(
        requested_actions=(
            RequestedActionItemV2(action=ExtractedActionV2.EXCHANGE, source_quote="교환"),
            RequestedActionItemV2(action=ExtractedActionV2.REFUND, source_quote="환불"),
        ),
        summary="교환 또는 환불 요청",
    )
    multiple.require_exact_source_quotes(
        customer_message="교환이 안 되면 환불해주세요", provider="contract"
    )
    assert [item.action for item in multiple.requested_actions] == [
        ExtractedActionV2.EXCHANGE,
        ExtractedActionV2.REFUND,
    ]
    assert LLMTextExtractionResultV2(summary="요청이 없음").requested_actions == ()


def test_policy_query_builder_is_strict_and_decision_free() -> None:
    result = PolicyQueryBuilderResult.model_validate(
        {
            "schema_version": "1.0",
            "queries": ["누액 교환 증거 조건"],
            "filters": {
                "policy_types": ["RETURN_EXCHANGE"],
                "product_categories": ["GENERAL"],
                "defect_types": ["LEAKAGE"],
                "document_status": "ACTIVE",
            },
        }
    )
    assert result.queries == ("누액 교환 증거 조건",)
    with pytest.raises(ValidationError):
        PolicyQueryBuilderResult.model_validate(
            {
                **result.model_dump(mode="json"),
                "recommended_decision": "APPROVE",
            }
        )


def test_grounded_explanation_rejects_unknown_citation_and_decision_fields() -> None:
    result = GroundedPolicyExplanation.model_validate(
        {
            "schema_version": "1.0",
            "applicable_evidence": [
                {"clause_id": "POLICY-REF:1.0.0:C1", "explanation": "검토 조건"}
            ],
            "unresolved_conditions": [],
        }
    )
    result.require_allowed_citations({"POLICY-REF:1.0.0:C1"})
    with pytest.raises(ValueError, match="supplied retrieval context"):
        result.require_allowed_citations({"POLICY-OTHER:1.0.0:C1"})
    with pytest.raises(ValidationError):
        GroundedPolicyExplanation.model_validate(
            {
                **result.model_dump(mode="json"),
                "final_decision": "REJECT",
            }
        )
