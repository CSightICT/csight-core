"""Opt-in contract probes against the host-native Local MLX service."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest

from app.bootstrap.dependencies import build_llm_provider
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import (
    GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_1,
    POLICY_QUERY_BUILDER_PROMPT_LOCAL_1,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_1,
)
from app.platform.analysis.enums import CustomerRequest, ExtractionIssueType
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMTextExtractionRequestV2,
    LLMTextExtractionResultV2,
)
from app.platform.grounding import (
    CitationPack,
    CitationSnapshot,
    GroundedExplanationInput,
)
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import (
    PolicyQueryBuilderInput,
    QueryStrategy,
    TrustedCaseMetadata,
)
from app.ports.llm import LLMProvider

pytestmark = pytest.mark.external_local_llm


def _provider() -> LLMProvider:
    if os.getenv("RUN_EXTERNAL_LOCAL_LLM_TESTS") != "1":
        pytest.skip("set RUN_EXTERNAL_LOCAL_LLM_TESTS=1 to use the Local MLX service")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    if settings.llm_provider != "mlx":
        pytest.fail("Local MLX tests require LLM_PROVIDER=mlx")
    return build_llm_provider(settings)


def test_local_mlx_extraction_v2_schema_and_metadata() -> None:
    result = _provider().extract_text_v2(
        LLMTextExtractionRequestV2(
            customer_message="용기 하단이 깨져 내용물이 샜습니다. 교환해주세요.",
            declared_requested_action=CustomerRequest.UNSPECIFIED,
        ),
        PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2_LOCAL_1,
    )
    assert result.metadata.provider_name == "mlx"
    assert result.metadata.model_revision == "938d8919941c6e7efd3c7150eff7fe9d12afa631"
    assert result.result.schema_version == "2.0"
    assert "<think>" not in result.model_dump_json().casefold()


def test_local_mlx_query_builder_schema() -> None:
    result = _provider().build_policy_queries(
        PolicyQueryBuilderInput(
            extraction=LLMTextExtractionResultV2(
                issue_types=(ExtractionIssueType.BREAKAGE,), summary="파손"
            ),
            completeness=CompletenessResult(
                system_missing_information=(),
                action_consistency=ActionConsistency.BOTH_UNSPECIFIED,
            ),
            trusted_metadata=TrustedCaseMetadata(
                product_category="GENERAL", days_since_purchase=3, available_image_count=1
            ),
        ),
        POLICY_QUERY_BUILDER_PROMPT_LOCAL_1,
    )
    assert result.metadata.provider_name == "mlx"
    assert 1 <= len(result.plan.queries) <= 3
    assert [query.query_id for query in result.plan.queries] == [
        f"Q{index}" for index in range(1, len(result.plan.queries) + 1)
    ]


def test_local_mlx_grounding_schema_and_allowlist() -> None:
    citation = CitationSnapshot(
        citation_id="CIT-001",
        rank=1,
        policy_clause_row_id="synthetic-row",
        policy_clause_id="POLICY-BRD-001:2.0.0:C1",
        document_id="POLICY-BRD-001",
        document_version="2.0.0",
        title="Synthetic policy",
        section_path=("Synthetic", "C1"),
        clause_type=ClauseType.RULE,
        text="파손이 확인되면 증거 자료와 구매 정보를 검토해야 합니다.",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_type="SYNTHETIC_REFERENCE",
        source_hash="b" * 64,
        query_strategy=QueryStrategy.RAW,
        matched_query_ids=("Q1",),
        retrieval_profile_hash="a" * 64,
    )
    pack = CitationPack(
        id="pack-local-external",
        tenant_id="tenant-local",
        case_id="case-local",
        retrieval_run_id="retrieval-local",
        retrieval_profile_hash="a" * 64,
        citations=(citation,),
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )
    result = _provider().explain_policy_grounded(
        GroundedExplanationInput(case_summary="파손 제품 문의", citation_pack=pack),
        GROUNDED_POLICY_EXPLANATION_PROMPT_LOCAL_1,
    )
    assert result.metadata.provider_name == "mlx"
    assert result.explanation.policy_statements
    assert {
        citation_id
        for statement in result.explanation.policy_statements
        for citation_id in statement.citation_ids
    } <= {"CIT-001"}
