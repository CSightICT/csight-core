"""Pure correctness tests for exact BM25, embeddings, and RRF."""

import math
from datetime import date
from typing import Any, cast

import pytest
import urllib3
from pydantic import ValidationError
from urllib3.exceptions import ReadTimeoutError

from app.adapters.retrieval import ExactBM25Retriever, KoreanPolicyTokenizerV1
from app.adapters.retrieval.embedding_http import HTTPEmbeddingProvider
from app.adapters.retrieval.rrf import ReciprocalRankFusionRetriever
from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingProviderUnavailableError,
    EmbeddingVector,
    HybridFusionProfile,
    LexicalProfile,
    PolicyClauseRecord,
    PolicySearchFilters,
    PolicySearchHit,
    PolicySearchQuery,
    RetrievalMode,
    serialize_policy_clause,
)

pytestmark = pytest.mark.unit


def clause(
    identifier: str,
    text: str,
    *,
    title: str = "교환 정책",
    section_path: tuple[str, ...] = ("교환", "조건"),
) -> PolicyClauseRecord:
    return PolicyClauseRecord(
        row_id=f"row-{identifier}",
        tenant_id="tenant-a",
        document_id="POLICY-A",
        document_version="1.0.0",
        title=title,
        clause_id=identifier,
        section_path=section_path,
        clause_type=ClauseType.RULE,
        text=text,
        policy_type="RETURN_EXCHANGE",
        product_categories=("GENERAL",),
        defect_types=("LEAKAGE",),
        actions=("REVIEW",),
        requires_human_review=False,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        document_status=DocumentStatus.ACTIVE,
        source_type="SYNTHETIC_REFERENCE",
        source_hash="a" * 64,
    )


def query() -> PolicySearchQuery:
    return PolicySearchQuery(
        tenant_id="tenant-a",
        query="누액 교환",
        as_of_date=date(2026, 2, 1),
        mode=RetrievalMode.LEXICAL,
        top_k=10,
    )


def dense_profile() -> DenseProfile:
    return DenseProfile(
        model_artifact="Qwen/Qwen3-Embedding-0.6B",
        model_revision="revision",
        embedding_dimension=2,
        pooling_strategy="last-token",
        query_instruction="instruction",
        max_query_tokens=8,
        max_document_tokens=8,
    )


def test_korean_tokenizer_is_nfkc_lower_deterministic_and_adds_bigrams() -> None:
    tokenizer = KoreanPolicyTokenizerV1()
    source = "\N{FULLWIDTH LATIN CAPITAL LETTER A}BC 누액 2026-02-01 C4.2"
    first = tokenizer.tokenize(source)
    assert first == tokenizer.tokenize(source)
    assert "abc" in first
    assert "2026-02-01" in first
    assert "ko2:누액" in first


def test_exact_bm25_formula_fixture_and_stable_tie_breaker() -> None:
    retriever = ExactBM25Retriever()
    candidates = (
        clause("C2", "누액 교환"),
        clause("C1", "누액 교환"),
        clause("C3", "파손", title="배송 정책", section_path=("배송", "안내")),
    )
    hits = retriever.retrieve(query=query(), candidates=candidates, profile=LexicalProfile())
    assert [hit.clause.clause_id for hit in hits] == ["C1", "C2"]
    assert hits[0].lexical_score == pytest.approx(hits[1].lexical_score)
    assert hits[0].lexical_score is not None and hits[0].lexical_score > 0


def test_filter_allowlists_reject_unknown_values() -> None:
    with pytest.raises(ValidationError):
        PolicySearchFilters(policy_types=("NOT_A_POLICY",))
    with pytest.raises(ValidationError):
        PolicySearchFilters(defect_types=("NOT_A_DEFECT",))


def test_embedding_vector_rejects_dimensionless_nan_inf_and_non_unit_norm() -> None:
    with pytest.raises(ValidationError):
        EmbeddingVector(values=(), model="m", model_revision="r", normalized=True)
    for value in (math.nan, math.inf):
        with pytest.raises(ValidationError):
            EmbeddingVector(values=(value,), model="m", model_revision="r", normalized=False)
    with pytest.raises(ValidationError):
        EmbeddingVector(values=(2.0, 0.0), model="m", model_revision="r", normalized=True)
    valid = EmbeddingVector(values=(1.001, 0.0), model="m", model_revision="r", normalized=True)
    assert valid.dimension == 2


def test_clause_serialization_excludes_tenant_and_internal_row_id() -> None:
    value = serialize_policy_clause(clause("C1", "누액 교환 조건"))
    assert "문서: 교환 정책" in value
    assert "본문: 누액 교환 조건" in value
    assert "tenant-a" not in value
    assert "row-C1" not in value


def test_rrf_deduplicates_and_uses_stable_rank_tie_breaker() -> None:
    first = clause("C1", "첫째")
    second = clause("C2", "둘째")
    lexical = (
        PolicySearchHit(clause=second, lexical_rank=1, lexical_score=2.0),
        PolicySearchHit(clause=first, lexical_rank=2, lexical_score=1.0),
    )
    dense = (
        PolicySearchHit(clause=first, dense_rank=1, dense_score=0.9),
        PolicySearchHit(clause=second, dense_rank=2, dense_score=0.8),
    )
    hits = ReciprocalRankFusionRetriever().fuse(
        lexical_hits=lexical,
        dense_hits=dense,
        profile=HybridFusionProfile(rrf_k=20),
        top_k=10,
    )
    assert len(hits) == 2
    assert {hit.clause.clause_id for hit in hits} == {"C1", "C2"}
    assert [hit.fusion_rank for hit in hits] == [1, 2]
    assert all(hit.lexical_rank is not None and hit.dense_rank is not None for hit in hits)


def test_embedding_http_timeout_is_bounded_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def request(_: object, method: str, url: str, **options: object) -> object:
        observed.update(options)
        raise ReadTimeoutError(cast(Any, None), url, "fixture timeout")

    monkeypatch.setattr(urllib3.PoolManager, "request", request)
    provider = HTTPEmbeddingProvider(base_url="http://embedding.test", timeout_seconds=7)
    with pytest.raises(EmbeddingProviderUnavailableError):
        provider.embed_query("누액 교환", dense_profile())
    timeout = observed["timeout"]
    assert isinstance(timeout, urllib3.Timeout)
    assert timeout.connect_timeout == 5.0
    assert timeout.read_timeout == 7
