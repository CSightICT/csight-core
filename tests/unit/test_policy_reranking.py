"""Policy reranker profile, serialization, allowlist, and application tests."""

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.adapters.reranking import MockPolicyRerankerAdapter
from app.application.policy_retrieval import SearchPolicyClauses
from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingVector,
    HybridFusionProfile,
    LexicalProfile,
    PolicyClauseRecord,
    PolicyRetrievalProfile,
    PolicySearchHit,
    PolicySearchQuery,
    RetrievalMode,
)
from app.platform.reranking import (
    DOCUMENT_TEMPLATE,
    MockRerankerMode,
    PolicyRerankerProfile,
    PolicyRerankRequest,
    PolicyRerankResult,
    PolicyRetrievalExecutionProfile,
    RerankCandidate,
    RerankerProviderInvalidResponseError,
    RerankScore,
    serialize_rerank_document,
    validate_rerank_result,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit


def profile() -> PolicyRerankerProfile:
    return PolicyRerankerProfile(
        provider_name="host_transformers",
        model_artifact="Qwen/Qwen3-Reranker-0.6B",
        model_revision="revision",
        instruction="retrieve policy clauses",
        instruction_hash="a" * 64,
        query_template_hash="b" * 64,
        document_template_hash="c" * 64,
        max_query_tokens=512,
        max_document_tokens=1024,
        max_pair_tokens=2048,
        candidate_k=20,
        final_k=10,
        batch_size=8,
        device="mps",
        score_semantics="normalized yes-vs-no pairwise relevance score",
    )


def clause(value: str = "C1") -> PolicyClauseRecord:
    return PolicyClauseRecord(
        row_id=f"row-{value}",
        tenant_id="tenant-secret",
        document_id="POLICY-A",
        document_version="1.0.0",
        title="교환 정책",
        clause_id=f"POLICY-A:1.0.0:{value}",
        section_path=("교환", value),
        clause_type=ClauseType.RULE,
        text=f"본문 {value}",
        policy_type="RETURN_EXCHANGE",
        product_categories=("GENERAL",),
        defect_types=("LEAKAGE",),
        actions=("REVIEW",),
        requires_human_review=False,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        document_status=DocumentStatus.ACTIVE,
        source_type="SYNTHETIC_REFERENCE",
        source_hash="d" * 64,
    )


def request() -> PolicyRerankRequest:
    return PolicyRerankRequest(
        query="누액 교환",
        candidates=(
            RerankCandidate(candidate_id="a", text="first", original_rank=1),
            RerankCandidate(candidate_id="b", text="second", original_rank=2),
        ),
        profile=profile(),
    )


def test_profile_hash_and_pair_serialization_are_stable_and_safe() -> None:
    assert profile().profile_hash == profile().profile_hash
    text = serialize_rerank_document(clause())
    assert text == DOCUMENT_TEMPLATE.format(
        title="교환 정책",
        section_path="교환 > C1",
        policy_type="RETURN_EXCHANGE",
        clause_type="RULE",
        text="본문 C1",
    )
    assert "tenant-secret" not in text
    assert "row-C1" not in text


def test_profile_rejects_invalid_token_and_top_k_contracts() -> None:
    with pytest.raises(ValidationError):
        profile().model_copy(update={"final_k": 30}).model_validate(
            {**profile().model_dump(), "final_k": 30}
        )
    with pytest.raises(ValidationError):
        PolicyRerankerProfile.model_validate(
            {**profile().model_dump(), "max_query_tokens": 1500, "max_document_tokens": 1024}
        )


def test_allowlist_rejects_unknown_duplicate_missing_rank_and_nonfinite_score() -> None:
    base = request()
    good = PolicyRerankResult(
        model="m",
        model_revision="revision",
        profile_version="1.0.0",
        scores=(
            RerankScore(candidate_id="b", original_rank=2, rerank_rank=1, rerank_score=0.9),
            RerankScore(candidate_id="a", original_rank=1, rerank_rank=2, rerank_score=0.2),
        ),
        latency_ms=1,
    )
    assert [value.candidate_id for value in validate_rerank_result(request=base, result=good)] == [
        "b",
        "a",
    ]
    mutations = (
        good.model_copy(update={"scores": (good.scores[0],)}),
        good.model_copy(
            update={
                "scores": (
                    good.scores[0],
                    good.scores[1].model_copy(update={"candidate_id": "unknown"}),
                )
            }
        ),
        good.model_copy(
            update={
                "scores": (
                    good.scores[0],
                    good.scores[0].model_copy(update={"rerank_rank": 2}),
                )
            }
        ),
        good.model_copy(
            update={
                "scores": (
                    good.scores[0],
                    good.scores[1].model_copy(update={"rerank_rank": 3}),
                )
            }
        ),
    )
    for value in mutations:
        with pytest.raises(RerankerProviderInvalidResponseError):
            validate_rerank_result(request=base, result=value)
    with pytest.raises(ValidationError):
        RerankScore(candidate_id="a", original_rank=1, rerank_rank=1, rerank_score=float("nan"))


def test_mock_is_deterministic_and_explicit_failures_are_normalized() -> None:
    adapter = MockPolicyRerankerAdapter()
    assert adapter.rerank(request()) == adapter.rerank(request())
    for mode in (MockRerankerMode.DUPLICATE_CANDIDATE, MockRerankerMode.UNKNOWN_CANDIDATE):
        result = MockPolicyRerankerAdapter(mode).rerank(request())
        with pytest.raises(RerankerProviderInvalidResponseError):
            validate_rerank_result(request=request(), result=result)


class _Profiles:
    def get_active_profile(self, tenant_id: str) -> PolicyRetrievalProfile:
        assert tenant_id == "tenant-a"
        return PolicyRetrievalProfile(
            lexical=LexicalProfile(),
            dense=DenseProfile(
                model_artifact="embedding",
                model_revision="embedding-revision",
                embedding_dimension=2,
                pooling_strategy="last-token",
                query_instruction="retrieve",
                max_query_tokens=10,
                max_document_tokens=10,
            ),
            fusion=HybridFusionProfile(rrf_k=20, lexical_weight=1.5, dense_weight=0.5),
            embedding_profile_id="embedding-id",
            index_version="1.0.0",
        )


class _Execution:
    def get_active_execution_profile(
        self, *, tenant_id: str, base_index_version: str
    ) -> PolicyRetrievalExecutionProfile:
        assert (tenant_id, base_index_version) == ("tenant-a", "1.0.0")
        return PolicyRetrievalExecutionProfile(
            profile_name="policy_retrieval_execution",
            profile_version="2.0.0",
            base_index_version="1.0.0",
            candidate_mode="HYBRID_RRF",
            candidate_k=20,
            final_k=10,
            status="ACTIVE",
            profile_hash="e" * 64,
            reranker=profile(),
        )


class _Clauses:
    observed_top_k = 0

    def candidates(self, query: PolicySearchQuery) -> tuple[PolicyClauseRecord, ...]:
        self.observed_top_k = query.top_k
        return (clause("C1"), clause("C2"))


class _Lexical:
    def retrieve(self, **kwargs: Any) -> tuple[PolicySearchHit, ...]:
        return tuple(
            PolicySearchHit(clause=value, lexical_rank=rank, lexical_score=1 / rank)
            for rank, value in enumerate(kwargs["candidates"], start=1)
        )


class _Embedding:
    def embed_query(self, value: str, profile: DenseProfile) -> EmbeddingVector:
        return EmbeddingVector(
            values=(1.0, 0.0), model="m", model_revision=profile.model_revision, normalized=True
        )

    def embed_documents(
        self, values: Sequence[str], profile: DenseProfile
    ) -> tuple[EmbeddingVector, ...]:
        return tuple(self.embed_query(value, profile) for value in values)


class _Dense:
    def retrieve(self, **kwargs: Any) -> tuple[PolicySearchHit, ...]:
        return (
            PolicySearchHit(clause=clause("C2"), dense_rank=1, dense_score=0.9),
            PolicySearchHit(clause=clause("C1"), dense_rank=2, dense_score=0.8),
        )

    def retrieve_least_similar(self, **kwargs: Any) -> tuple[PolicySearchHit, ...]:
        return ()

    def retrieve_closest_to_score(self, **kwargs: Any) -> tuple[PolicySearchHit, ...]:
        return ()


class _Hybrid:
    def fuse(self, **kwargs: Any) -> tuple[PolicySearchHit, ...]:
        return (
            PolicySearchHit(clause=clause("C1"), fusion_rank=1, fusion_score=0.9),
            PolicySearchHit(clause=clause("C2"), fusion_rank=2, fusion_score=0.8),
        )[: kwargs["top_k"]]


def test_application_uses_server_profile_candidate_k_then_reranks_only_allowlisted_hits() -> None:
    clauses = _Clauses()
    service = SearchPolicyClauses(
        clauses=clauses,
        profiles=_Profiles(),
        lexical=_Lexical(),
        embeddings=_Embedding(),
        dense=_Dense(),
        hybrid=_Hybrid(),
        execution_profiles=_Execution(),
        reranker=MockPolicyRerankerAdapter(),
    )
    result = service.execute(
        principal=Principal(
            user_id="user-a",
            tenant_id="tenant-a",
            email="reviewer@example.test",
            display_name="Reviewer",
            roles=frozenset({Role.REVIEWER}),
        ),
        query=PolicySearchQuery(
            tenant_id="tenant-a",
            query="누액 교환",
            as_of_date=date(2026, 2, 1),
            mode=RetrievalMode.HYBRID_RERANKED,
            top_k=1,
        ),
    )
    assert clauses.observed_top_k == 20
    assert len(result.hits) == 1
    assert result.hits[0].candidate_rank in {1, 2}
    assert result.hits[0].rerank_rank == 1
    assert result.hits[0].reranker_profile == "qwen3_policy_reranker:1.0.0"
    assert cast(Any, result.hits[0]).clause.tenant_id == "tenant-secret"
