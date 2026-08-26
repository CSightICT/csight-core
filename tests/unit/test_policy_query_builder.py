"""Query-plan, deterministic rule, and multi-query fusion invariants."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.domains.product_defect_cs.query_builder import build_deterministic_query_plan
from app.platform.analysis.enums import DefectLocation, ExtractionIssueType
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMTextClaimV2,
    LLMTextExtractionResultV2,
    SystemMissingInformation,
)
from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import PolicyClauseRecord, PolicySearchHit
from app.platform.query_builder import (
    PolicyQueryBuilderInput,
    PolicyQueryPlan,
    TrustedCaseMetadata,
    fuse_multi_query_hits,
)


def _input() -> PolicyQueryBuilderInput:
    return PolicyQueryBuilderInput(
        extraction=LLMTextExtractionResultV2(
            issue_types=(ExtractionIssueType.BREAKAGE, ExtractionIssueType.LEAKAGE),
            claims=(
                LLMTextClaimV2(
                    type=ExtractionIssueType.BREAKAGE,
                    location=DefectLocation.BOTTOM,
                    description="하단 파손",
                    source_quote="하단이 깨짐",
                ),
            ),
            summary="파손 및 누액",
        ),
        completeness=CompletenessResult(
            system_missing_information=(SystemMissingInformation.IMAGE_EVIDENCE,),
            action_consistency=ActionConsistency.BOTH_UNSPECIFIED,
        ),
        trusted_metadata=TrustedCaseMetadata(
            product_category="GENERAL", days_since_purchase=3, available_image_count=0
        ),
    )


def _hit(clause_id: str, *, document: str = "POLICY-1", version: str = "1.0.0") -> PolicySearchHit:
    return PolicySearchHit(
        clause=PolicyClauseRecord(
            row_id=clause_id,
            tenant_id="tenant-a",
            document_id=document,
            document_version=version,
            title="Synthetic",
            clause_id=clause_id,
            section_path=("Synthetic", "C1"),
            clause_type=ClauseType.RULE,
            text="synthetic reference clause",
            policy_type="RETURN_EXCHANGE",
            product_categories=("GENERAL",),
            defect_types=("BREAKAGE",),
            actions=("REVIEW",),
            requires_human_review=False,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            document_status=DocumentStatus.ACTIVE,
            source_type="SYNTHETIC_REFERENCE",
            source_hash="a" * 64,
        ),
        fusion_rank=1,
        fusion_score=0.1,
    )


def test_deterministic_query_builder_is_stable_and_adds_evidence_query() -> None:
    first = build_deterministic_query_plan(_input())
    second = build_deterministic_query_plan(_input())

    assert first == second
    assert first.content_hash == second.content_hash
    assert [query.query_id for query in first.queries] == ["Q1", "Q2"]
    assert first.queries[1].purpose == "EVIDENCE_REQUIREMENT"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "queries": [{"query_id": "Q1", "purpose": "PRIMARY_POLICY", "text": "valid query"}],
            "tenant_id": "bad",
        },
        {
            "queries": [
                {"query_id": "Q1", "purpose": "PRIMARY_POLICY", "text": "same"},
                {"query_id": "Q2", "purpose": "PROCEDURE", "text": "same"},
            ]
        },
        {"queries": [{"query_id": "Q1", "purpose": "UNKNOWN", "text": "valid query"}]},
        {"queries": []},
    ],
)
def test_query_plan_rejects_forbidden_invalid_duplicate_or_empty_output(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PolicyQueryPlan.model_validate(payload)


def test_multi_query_rrf_preserves_provenance_and_version_identity() -> None:
    shared = _hit("C1")
    other_version = _hit("C1", version="2.0.0")
    fused = fuse_multi_query_hits(
        results=(("Q1", (shared, other_version)), ("Q2", (shared,))),
        top_k=10,
    )

    assert len(fused) == 2
    assert fused[0].matched_query_ids == ("Q1", "Q2")
    assert fused[0].best_query_rank == 1
    assert fused[0].hit.clause.document_version == "1.0.0"
    assert fused[1].hit.clause.document_version == "2.0.0"
