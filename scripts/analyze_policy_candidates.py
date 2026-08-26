"""Measure frozen HYBRID_RRF candidate recall and oracle reranking upper bounds."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import TenantModel
from app.adapters.persistence.policy_repositories import (
    SQLAlchemyDenseRetriever,
    SQLAlchemyPolicyClauseRepository,
)
from app.adapters.persistence.session import create_session_factory
from app.adapters.retrieval import ExactBM25Retriever, HTTPEmbeddingProvider
from app.adapters.retrieval.rrf import ReciprocalRankFusionRetriever
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import (
    DenseProfile,
    HybridFusionProfile,
    LexicalProfile,
    PolicySearchFilters,
    PolicySearchHit,
    PolicySearchQuery,
    RetrievalMode,
    stable_json_hash,
)
from scripts.build_policy_embeddings import PROFILE_ID

GOLD_PATH = Path("evaluation/policy_retrieval_v1/gold.jsonl")
BASE_PROFILE_PATH = Path("evaluation/results/policy_retrieval_v1/retrieval_profile_v1.json")
RESULT_ROOT = Path("evaluation/results/policy_reranker_v1")
CANDIDATE_K_VALUES = (10, 20, 30, 50)
FINAL_K = 10


def reciprocal_rank(candidate_ids: tuple[str, ...], relevant: frozenset[str]) -> float:
    return next(
        (1.0 / rank for rank, value in enumerate(candidate_ids, start=1) if value in relevant),
        0.0,
    )


def ndcg(candidate_ids: tuple[str, ...], relevant: frozenset[str], cutoff: int = 10) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, value in enumerate(candidate_ids[:cutoff], start=1)
        if value in relevant
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(cutoff, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def oracle_order(candidate_ids: tuple[str, ...], relevant: frozenset[str]) -> tuple[str, ...]:
    """Place known relevant candidates first, preserving order within both groups."""

    return tuple(value for value in candidate_ids if value in relevant) + tuple(
        value for value in candidate_ids if value not in relevant
    )


def candidate_metrics(rows: tuple[dict[str, Any], ...]) -> dict[str, float | int]:
    recalls: list[float] = []
    exact: list[float] = []
    zero: list[float] = []
    hard_negative: list[float] = []
    counts: list[int] = []
    oracle_recall: list[float] = []
    oracle_mrr: list[float] = []
    oracle_ndcg: list[float] = []
    oracle_exact: list[float] = []
    for row in rows:
        relevant = frozenset(str(value) for value in row["relevant_clause_ids"])
        candidates = tuple(str(value) for value in row["candidate_ids"])
        hard = frozenset(str(value) for value in row["hard_negative_clause_ids"])
        matched = len(relevant.intersection(candidates))
        recalls.append(matched / len(relevant))
        exact.append(float(relevant.issubset(candidates)))
        zero.append(float(not candidates))
        hard_negative.append(float(bool(hard.intersection(candidates))))
        counts.append(len(candidates))
        oracle = oracle_order(candidates, relevant)[:FINAL_K]
        oracle_matched = len(relevant.intersection(oracle))
        oracle_recall.append(oracle_matched / len(relevant))
        oracle_mrr.append(reciprocal_rank(oracle, relevant))
        oracle_ndcg.append(ndcg(oracle, relevant))
        oracle_exact.append(float(relevant.issubset(oracle)))
    return {
        "query_count": len(rows),
        "candidate_recall": statistics.fmean(recalls),
        "candidate_exact_coverage": statistics.fmean(exact),
        "zero_candidate_rate": statistics.fmean(zero),
        "hard_negative_inclusion_rate": statistics.fmean(hard_negative),
        "average_candidate_count": statistics.fmean(counts),
        "oracle_recall_at_10": statistics.fmean(oracle_recall),
        "oracle_mrr_at_10": statistics.fmean(oracle_mrr),
        "oracle_ndcg_at_10": statistics.fmean(oracle_ndcg),
        "oracle_exact_coverage_at_10": statistics.fmean(oracle_exact),
    }


def _query(payload: dict[str, Any], tenant_id: str) -> PolicySearchQuery:
    expected = payload["expected_filters"]
    case = payload["case"]
    return PolicySearchQuery(
        tenant_id=tenant_id,
        query=payload["query_text"],
        as_of_date=payload["as_of_date"],
        mode=RetrievalMode.HYBRID,
        top_k=max(CANDIDATE_K_VALUES),
        filters=PolicySearchFilters(
            policy_types=tuple(expected.get("policy_types", ())),
            product_categories=(case["product_category"],),
            defect_types=tuple(expected.get("defect_types", ())),
        ),
    )


def _ids(hits: tuple[PolicySearchHit, ...]) -> tuple[str, ...]:
    return tuple(hit.clause.clause_id for hit in hits)


def _load_profiles() -> tuple[dict[str, Any], LexicalProfile, DenseProfile, HybridFusionProfile]:
    payload = json.loads(BASE_PROFILE_PATH.read_text(encoding="utf-8"))
    if not payload.get("test_evaluated"):
        raise ValueError("Sprint 4B retrieval profile is not frozen and test-locked")
    return (
        payload,
        LexicalProfile.model_validate(payload["lexical"]),
        DenseProfile.model_validate(payload["embedding"]),
        HybridFusionProfile.model_validate(payload["fusion"]),
    )


def _select_candidate_k(metrics_by_k: dict[str, dict[str, float | int]]) -> int:
    """Choose the smallest K with maximum Dev recall, then maximum exact coverage."""

    best_recall = max(float(value["candidate_recall"]) for value in metrics_by_k.values())
    recall_winners = {
        key: value
        for key, value in metrics_by_k.items()
        if math.isclose(float(value["candidate_recall"]), best_recall)
    }
    best_exact = max(float(value["candidate_exact_coverage"]) for value in recall_winners.values())
    return min(
        int(key)
        for key, value in recall_winners.items()
        if math.isclose(float(value["candidate_exact_coverage"]), best_exact)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    arguments = parser.parse_args()
    output_path = RESULT_ROOT / f"candidate_upper_bound_{arguments.split}.json"
    freeze_path = RESULT_ROOT / "candidate_pool_profile_v1.json"
    if output_path.exists():
        raise ValueError(f"candidate upper bound already evaluated: {output_path}")
    if arguments.split == "test" and not freeze_path.exists():
        raise ValueError("freeze the Dev candidate pool before evaluating Test")

    base_profile, lexical_profile, dense_profile, fusion_profile = _load_profiles()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        tenant_ids = {
            row.slug: str(row.id)
            for row in session.scalars(
                select(TenantModel).where(
                    TenantModel.slug.in_(("csight-demo-brand", "csight-demo-retail"))
                )
            )
        }
    payloads = tuple(
        json.loads(line)
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["split"] == arguments.split
    )
    clauses = SQLAlchemyPolicyClauseRepository(factory)
    dense = SQLAlchemyDenseRetriever(factory)
    lexical = ExactBM25Retriever()
    fusion = ReciprocalRankFusionRetriever()
    provider = HTTPEmbeddingProvider(
        base_url=arguments.embedding_base_url,
        timeout_seconds=180,
    )
    rows_by_k: dict[int, list[dict[str, Any]]] = {value: [] for value in CANDIDATE_K_VALUES}
    for payload in payloads:
        query = _query(payload, tenant_ids[str(payload["tenant_id"])])
        candidates = clauses.candidates(query)
        lexical_hits = lexical.retrieve(
            query=query,
            candidates=candidates,
            profile=lexical_profile,
        )
        vector = provider.embed_query(query.query, dense_profile)
        dense_hits = dense.retrieve(
            query=query,
            query_vector=vector,
            embedding_profile_id=str(PROFILE_ID),
        )
        for candidate_k in CANDIDATE_K_VALUES:
            hybrid = fusion.fuse(
                lexical_hits=lexical_hits[:candidate_k],
                dense_hits=dense_hits[:candidate_k],
                profile=fusion_profile,
                top_k=candidate_k,
            )
            candidate_ids = _ids(hybrid)
            if len(candidate_ids) != len(set(candidate_ids)):
                raise ValueError(f"duplicate candidate for {payload['query_id']} K={candidate_k}")
            rows_by_k[candidate_k].append(
                {
                    "query_id": payload["query_id"],
                    "candidate_ids": candidate_ids,
                    "relevant_clause_ids": payload["relevant_clause_ids"],
                    "hard_negative_clause_ids": payload["hard_negative_clause_ids"],
                }
            )

    metrics_by_k = {
        str(value): candidate_metrics(tuple(rows_by_k[value])) for value in CANDIDATE_K_VALUES
    }
    selected_k = _select_candidate_k(metrics_by_k) if arguments.split == "dev" else None
    result = {
        "artifact_version": "1.0.0",
        "split": arguments.split,
        "diagnostic_only": True,
        "oracle_is_not_a_retrieval_method": True,
        "candidate_mode": "HYBRID_RRF",
        "candidate_k_values": list(CANDIDATE_K_VALUES),
        "final_k": FINAL_K,
        "base_profile_hash": stable_json_hash(base_profile),
        "corpus_hash": base_profile["corpus_hash"],
        "retrieval_dataset_hash": base_profile["retrieval_dataset_hash"],
        "metrics_by_candidate_k": metrics_by_k,
        "per_query_by_candidate_k": {str(value): rows_by_k[value] for value in CANDIDATE_K_VALUES},
    }
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if arguments.split == "dev":
        assert selected_k is not None
        frozen = {
            "profile_name": "policy_candidate_pool",
            "profile_version": "1.0.0",
            "candidate_retrieval_profile": "policy_retrieval_v1:1.0.0",
            "candidate_mode": "HYBRID_RRF",
            "candidate_k": selected_k,
            "final_k": FINAL_K,
            "base_index_version": "1.0.0",
            "hybrid_profile_hash": stable_json_hash(base_profile["fusion"]),
            "corpus_hash": base_profile["corpus_hash"],
            "retrieval_dataset_hash": base_profile["retrieval_dataset_hash"],
            "selection_rule": "smallest K at maximum Dev candidate recall then exact coverage",
            "test_used_for_selection": False,
        }
        frozen["profile_hash"] = stable_json_hash(frozen)
        freeze_path.write_text(
            json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps({"split": arguments.split, "selected_k": selected_k, **metrics_by_k}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
