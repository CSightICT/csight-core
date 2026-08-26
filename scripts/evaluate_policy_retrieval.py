"""Tune on dev, freeze once, then evaluate the locked policy retrieval test split."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import PolicyClauseModel, PolicyIndexVersionModel, TenantModel
from app.adapters.persistence.policy_repositories import (
    SQLAlchemyDenseRetriever,
    SQLAlchemyPolicyClauseRepository,
)
from app.adapters.persistence.session import create_session_factory, session_scope
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
from scripts.build_policy_embeddings import (
    INDEX_NAME,
    MODEL_ARTIFACT,
    MODEL_REVISION,
    PROFILE_ID,
    QUERY_INSTRUCTION,
    TEMPLATE_CONTRACT,
)

ROOT = Path("evaluation/results/policy_retrieval_v1")
GOLD_PATH = Path("evaluation/policy_retrieval_v1/gold.jsonl")
DATASET_MANIFEST = Path("evaluation/policy_retrieval_v1/manifest.json")
CORPUS_MANIFEST = Path("data/policy_corpus/manifests/policy_corpus_v1.json")


@dataclass(frozen=True, slots=True)
class GoldQuery:
    payload: dict[str, Any]
    tenant_uuid: str

    @property
    def query_id(self) -> str:
        return str(self.payload["query_id"])

    @property
    def relevant(self) -> frozenset[str]:
        return frozenset(self.payload["relevant_clause_ids"])


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    gold: GoldQuery
    hits: dict[str, tuple[PolicySearchHit, ...]]
    latency_ms: dict[str, float]
    deterministic: bool


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def load_gold(split: str, tenant_ids: dict[str, str]) -> tuple[GoldQuery, ...]:
    return tuple(
        GoldQuery(payload=value, tenant_uuid=tenant_ids[str(value["tenant_id"])])
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        for value in [json.loads(line)]
        if value["split"] == split
    )


def domain_query(gold: GoldQuery, *, mode: RetrievalMode) -> PolicySearchQuery:
    expected = gold.payload["expected_filters"]
    case = gold.payload["case"]
    return PolicySearchQuery(
        tenant_id=gold.tenant_uuid,
        query=gold.payload["query_text"],
        as_of_date=gold.payload["as_of_date"],
        mode=mode,
        top_k=10,
        filters=PolicySearchFilters(
            policy_types=tuple(expected.get("policy_types", ())),
            product_categories=(case["product_category"],),
            defect_types=tuple(expected.get("defect_types", ())),
        ),
    )


def evaluate_split(
    *,
    gold: tuple[GoldQuery, ...],
    clause_repository: SQLAlchemyPolicyClauseRepository,
    dense_retriever: SQLAlchemyDenseRetriever,
    embedding_provider: HTTPEmbeddingProvider,
    lexical_profile: LexicalProfile,
    dense_profile: DenseProfile,
    fusion_profile: HybridFusionProfile,
) -> tuple[QueryOutcome, ...]:
    lexical = ExactBM25Retriever()
    fusion = ReciprocalRankFusionRetriever()
    outcomes: list[QueryOutcome] = []
    for item in gold:
        lexical_query = domain_query(item, mode=RetrievalMode.LEXICAL)
        started = time.perf_counter()
        candidates = clause_repository.candidates(lexical_query)
        lexical_hits = lexical.retrieve(
            query=lexical_query, candidates=candidates, profile=lexical_profile
        )
        lexical_latency = (time.perf_counter() - started) * 1000

        dense_query = lexical_query.model_copy(update={"mode": RetrievalMode.DENSE})
        started = time.perf_counter()
        vector = embedding_provider.embed_query(dense_query.query, dense_profile)
        dense_hits = dense_retriever.retrieve(
            query=dense_query,
            query_vector=vector,
            embedding_profile_id=str(PROFILE_ID),
        )
        dense_latency = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        hybrid_hits = fusion.fuse(
            lexical_hits=lexical_hits,
            dense_hits=dense_hits,
            profile=fusion_profile,
            top_k=10,
        )
        fusion_latency = (time.perf_counter() - started) * 1000

        lexical_again = lexical.retrieve(
            query=lexical_query, candidates=candidates, profile=lexical_profile
        )
        dense_again = dense_retriever.retrieve(
            query=dense_query,
            query_vector=vector,
            embedding_profile_id=str(PROFILE_ID),
        )
        hybrid_again = fusion.fuse(
            lexical_hits=lexical_again,
            dense_hits=dense_again,
            profile=fusion_profile,
            top_k=10,
        )
        deterministic = all(
            _signature(first) == _signature(second)
            for first, second in (
                (lexical_hits, lexical_again),
                (dense_hits, dense_again),
                (hybrid_hits, hybrid_again),
            )
        )
        outcomes.append(
            QueryOutcome(
                gold=item,
                hits={
                    "LEXICAL_BM25": lexical_hits,
                    "DENSE_QWEN3": dense_hits,
                    "HYBRID_RRF": hybrid_hits,
                },
                latency_ms={
                    "LEXICAL_BM25": lexical_latency,
                    "DENSE_QWEN3": dense_latency,
                    "HYBRID_RRF": lexical_latency + dense_latency + fusion_latency,
                },
                deterministic=deterministic,
            )
        )
    return tuple(outcomes)


def _signature(hits: tuple[PolicySearchHit, ...]) -> tuple[str, ...]:
    return tuple(hit.clause.clause_id for hit in hits)


def tune_lexical(
    gold: tuple[GoldQuery, ...], clause_repository: SQLAlchemyPolicyClauseRepository
) -> LexicalProfile:
    retriever = ExactBM25Retriever()
    candidate_cache = {
        item.query_id: clause_repository.candidates(domain_query(item, mode=RetrievalMode.LEXICAL))
        for item in gold
    }
    choices: list[tuple[tuple[float, ...], LexicalProfile]] = []
    for k1 in (0.9, 1.2, 1.5, 1.8):
        for b in (0.3, 0.5, 0.75, 0.9):
            profile = LexicalProfile(k1=k1, b=b)
            hits = {
                item.query_id: retriever.retrieve(
                    query=domain_query(item, mode=RetrievalMode.LEXICAL),
                    candidates=candidate_cache[item.query_id],
                    profile=profile,
                )
                for item in gold
            }
            score = _selection_score(gold, hits)
            choices.append(((*score, -k1, -b), profile))
    return max(choices, key=lambda value: value[0])[1]


def tune_fusion(
    outcomes: tuple[QueryOutcome, ...],
) -> HybridFusionProfile:
    retriever = ReciprocalRankFusionRetriever()
    choices: list[tuple[tuple[float, ...], HybridFusionProfile]] = []
    gold = tuple(outcome.gold for outcome in outcomes)
    for rrf_k in (20, 40, 60, 80):
        for lexical_weight in (0.5, 1.0, 1.5):
            for dense_weight in (0.5, 1.0, 1.5):
                profile = HybridFusionProfile(
                    rrf_k=rrf_k,
                    lexical_weight=lexical_weight,
                    dense_weight=dense_weight,
                )
                hits = {
                    outcome.gold.query_id: retriever.fuse(
                        lexical_hits=outcome.hits["LEXICAL_BM25"],
                        dense_hits=outcome.hits["DENSE_QWEN3"],
                        profile=profile,
                        top_k=10,
                    )
                    for outcome in outcomes
                }
                score = _selection_score(gold, hits)
                choices.append(
                    (
                        (*score, -rrf_k, -lexical_weight, -dense_weight),
                        profile,
                    )
                )
    return max(choices, key=lambda value: value[0])[1]


def _selection_score(
    gold: tuple[GoldQuery, ...], hits: dict[str, tuple[PolicySearchHit, ...]]
) -> tuple[float, ...]:
    recalls5: list[float] = []
    recalls10: list[float] = []
    reciprocal: list[float] = []
    ndcgs: list[float] = []
    for item in gold:
        ids = tuple(hit.clause.clause_id for hit in hits[item.query_id])
        recalls5.append(len(item.relevant.intersection(ids[:5])) / len(item.relevant))
        recalls10.append(len(item.relevant.intersection(ids[:10])) / len(item.relevant))
        reciprocal.append(reciprocal_rank(ids, item.relevant))
        ndcgs.append(ndcg(ids[:10], item.relevant))
    return (
        statistics.fmean(recalls5),
        statistics.fmean(recalls10),
        statistics.fmean(reciprocal),
        statistics.fmean(ndcgs),
    )


def metrics(outcomes: tuple[QueryOutcome, ...], mode: str) -> dict[str, Any]:
    values: dict[str, list[float]] = defaultdict(list)
    violation_counts: dict[str, int] = defaultdict(int)
    latencies: list[float] = []
    for outcome in outcomes:
        relevant = outcome.gold.relevant
        hits = outcome.hits[mode]
        ids = tuple(hit.clause.clause_id for hit in hits)
        for k in (1, 3, 5, 10):
            matched = len(relevant.intersection(ids[:k]))
            values[f"recall_at_{k}"].append(matched / len(relevant))
            values[f"precision_at_{k}"].append(matched / k)
            values[f"exact_gold_coverage_at_{k}"].append(float(relevant.issubset(ids[:k])))
        values["mrr_at_10"].append(reciprocal_rank(ids[:10], relevant))
        values["ndcg_at_10"].append(ndcg(ids[:10], relevant))
        values["zero_result_rate"].append(float(not ids))
        hard = frozenset(outcome.gold.payload["hard_negative_clause_ids"])
        values["hard_negative_hit_rate_at_5"].append(float(bool(hard.intersection(ids[:5]))))
        violation_counts["cross_tenant"] += sum(
            hit.clause.tenant_id != outcome.gold.tenant_uuid for hit in hits
        )
        violation_counts["future"] += sum(
            hit.clause.effective_from
            > domain_query(outcome.gold, mode=RetrievalMode.LEXICAL).as_of_date
            for hit in hits
        )
        violation_counts["retired"] += sum(
            hit.clause.document_status.value != "ACTIVE" for hit in hits
        )
        violation_counts["duplicate"] += len(ids) - len(set(ids))
        relevant_versions = {tuple(clause_id.split(":")[:2]) for clause_id in outcome.gold.relevant}
        violation_counts["wrong_version"] += sum(
            (hit.clause.document_id, hit.clause.document_version) not in relevant_versions
            and any(hit.clause.document_id == document for document, _ in relevant_versions)
            for hit in hits
        )
        values["deterministic_ranking"].append(float(outcome.deterministic))
        latencies.append(outcome.latency_ms[mode])
    result = {key: statistics.fmean(items) for key, items in sorted(values.items())}
    denominator = max(1, sum(len(outcome.hits[mode]) for outcome in outcomes))
    result.update(
        {
            "wrong_version_retrieval_rate": violation_counts["wrong_version"] / denominator,
            "future_policy_retrieval_rate": violation_counts["future"] / denominator,
            "retired_policy_retrieval_rate": violation_counts["retired"] / denominator,
            "cross_tenant_retrieval_rate": violation_counts["cross_tenant"] / denominator,
            "duplicate_clause_hit_count": violation_counts["duplicate"],
            "latency_ms_p50": statistics.median(latencies),
            "latency_ms_p95": percentile(latencies, 0.95),
            "query_count": len(outcomes),
        }
    )
    return result


def reciprocal_rank(ids: tuple[str, ...], relevant: frozenset[str]) -> float:
    return next((1.0 / rank for rank, value in enumerate(ids, start=1) if value in relevant), 0.0)


def ndcg(ids: tuple[str, ...], relevant: frozenset[str], cutoff: int = 10) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1) for rank, value in enumerate(ids, start=1) if value in relevant
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(cutoff, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def write_results(
    *,
    split: str,
    outcomes: tuple[QueryOutcome, ...],
    lexical: LexicalProfile,
    dense: DenseProfile,
    fusion: HybridFusionProfile,
) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    all_metrics = {mode: metrics(outcomes, mode) for mode in outcomes[0].hits}
    (ROOT / f"{split}_metrics.json").write_text(
        json.dumps(all_metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (ROOT / f"{split}_per_query.jsonl").open("w", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(
                json.dumps(
                    {
                        "query_id": outcome.gold.query_id,
                        "tenant_id": outcome.gold.payload["tenant_id"],
                        "scenario": outcome.gold.payload["scenario"],
                        "relevant_clause_ids": sorted(outcome.gold.relevant),
                        "ranks": {
                            mode: [hit.clause.clause_id for hit in hits]
                            for mode, hits in outcome.hits.items()
                        },
                        "latency_ms": outcome.latency_ms,
                        "deterministic": outcome.deterministic,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    _write_reports(split, outcomes, all_metrics, lexical, dense, fusion)


def _write_reports(
    split: str,
    outcomes: tuple[QueryOutcome, ...],
    all_metrics: dict[str, Any],
    lexical: LexicalProfile,
    dense: DenseProfile,
    fusion: HybridFusionProfile,
) -> None:
    misses = [
        outcome.gold.query_id
        for outcome in outcomes
        if not outcome.gold.relevant.issubset(
            {hit.clause.clause_id for hit in outcome.hits["HYBRID_RRF"][:10]}
        )
    ]
    (ROOT / "error_analysis.md").write_text(
        "# Retrieval error analysis\n\n"
        f"Latest evaluated split: `{split}`. Hybrid queries without complete Gold@10: "
        f"{len(misses)}/{len(outcomes)}.\n\n"
        + "\n".join(f"- `{query_id}`" for query_id in misses)
        + "\n",
        encoding="utf-8",
    )
    slices: dict[str, list[QueryOutcome]] = defaultdict(list)
    for outcome in outcomes:
        payload = outcome.gold.payload
        slices[f"tenant:{payload['tenant_id']}"].append(outcome)
        for value in payload["expected_filters"].get("policy_types", ()):
            slices[f"policy_type:{value}"].append(outcome)
        for value in payload["expected_filters"].get("defect_types", ()):
            slices[f"defect_type:{value}"].append(outcome)
        slices["multiple_relevant" if len(outcome.gold.relevant) > 1 else "single_relevant"].append(
            outcome
        )
        slices[f"scenario:{payload['scenario']}"].append(outcome)
        if payload["hard_negative_clause_ids"]:
            slices["hard_negative"].append(outcome)
    slice_payload = {
        key: {
            "query_count": len(items),
            "hybrid_recall_at_5": metrics(tuple(items), "HYBRID_RRF")["recall_at_5"],
            "hybrid_mrr_at_10": metrics(tuple(items), "HYBRID_RRF")["mrr_at_10"],
        }
        for key, items in sorted(slices.items())
    }
    (ROOT / "slice_analysis.md").write_text(
        "# Retrieval slice analysis\n\n```json\n"
        + json.dumps(slice_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    latency = {
        mode: {"p50_ms": value["latency_ms_p50"], "p95_ms": value["latency_ms_p95"]}
        for mode, value in all_metrics.items()
    }
    (ROOT / "latency_report.md").write_text(
        "# Retrieval latency report\n\n```json\n"
        + json.dumps(latency, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    (ROOT / "retrieval_baseline_report.md").write_text(
        "# Policy retrieval baseline\n\n"
        f"Split `{split}`; lexical `{lexical.identifier}` k1={lexical.k1}, b={lexical.b}; "
        f"dense `{dense.identifier}` revision `{dense.model_revision}`; fusion "
        f"`{fusion.identifier}` k={fusion.rrf_k}, "
        f"weights={fusion.lexical_weight}/{fusion.dense_weight}.\n\n"
        "This report measures retrieval only and contains no policy decision.\n",
        encoding="utf-8",
    )


def freeze_profile(
    *, lexical: LexicalProfile, dense: DenseProfile, fusion: HybridFusionProfile
) -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    payload = {
        "profile_name": "policy_retrieval_v1",
        "profile_version": "1.0.0",
        "frozen_at": datetime.now(UTC).isoformat(),
        "corpus_hash": corpus["source_hash"],
        "retrieval_dataset_hash": dataset["content_hash"],
        "lexical": lexical.model_dump(mode="json"),
        "embedding": dense.model_dump(mode="json"),
        "query_instruction_hash": stable_json_hash(QUERY_INSTRUCTION),
        "document_serialization": {
            "name": "policy_clause_passage",
            "version": "1.0.0",
            "template": TEMPLATE_CONTRACT,
            "template_hash": stable_json_hash(TEMPLATE_CONTRACT),
        },
        "fusion": fusion.model_dump(mode="json"),
        "code_commit": commit,
        "sprint_4b_worktree_uncommitted": True,
        "test_evaluated": False,
    }
    (ROOT / "retrieval_profile_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def load_profile() -> tuple[LexicalProfile, DenseProfile, HybridFusionProfile]:
    payload = json.loads((ROOT / "retrieval_profile_v1.json").read_text(encoding="utf-8"))
    return (
        LexicalProfile.model_validate(payload["lexical"]),
        DenseProfile.model_validate(payload["embedding"]),
        HybridFusionProfile.model_validate(payload["fusion"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--tune-and-freeze", action="store_true")
    arguments = parser.parse_args()
    if arguments.split == "dev" and not arguments.tune_and_freeze:
        raise ValueError("dev evaluation requires --tune-and-freeze")
    if arguments.split == "test" and arguments.tune_and_freeze:
        raise ValueError("locked test evaluation cannot tune")
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
        all_clause_ids = frozenset(session.scalars(select(PolicyClauseModel.clause_id)))
    all_gold = tuple(
        json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
    )
    gold_ids = {value for item in all_gold for value in item["relevant_clause_ids"]}
    if not gold_ids.issubset(all_clause_ids):
        raise ValueError("Gold Clause ID validity is below 100%")
    gold = load_gold(arguments.split, tenant_ids)
    clauses = SQLAlchemyPolicyClauseRepository(factory)
    dense_retriever = SQLAlchemyDenseRetriever(factory)
    provider = HTTPEmbeddingProvider(base_url=arguments.embedding_base_url, timeout_seconds=180)
    dense_profile = DenseProfile(
        model_artifact=MODEL_ARTIFACT,
        model_revision=MODEL_REVISION,
        embedding_dimension=1024,
        pooling_strategy="last-token",
        normalize_embeddings=True,
        query_instruction=QUERY_INSTRUCTION,
        max_query_tokens=8192,
        max_document_tokens=8192,
    )
    if arguments.split == "dev":
        lexical_profile = tune_lexical(gold, clauses)
        provisional = evaluate_split(
            gold=gold,
            clause_repository=clauses,
            dense_retriever=dense_retriever,
            embedding_provider=provider,
            lexical_profile=lexical_profile,
            dense_profile=dense_profile,
            fusion_profile=HybridFusionProfile(),
        )
        fusion_profile = tune_fusion(provisional)
        outcomes = evaluate_split(
            gold=gold,
            clause_repository=clauses,
            dense_retriever=dense_retriever,
            embedding_provider=provider,
            lexical_profile=lexical_profile,
            dense_profile=dense_profile,
            fusion_profile=fusion_profile,
        )
        freeze_profile(lexical=lexical_profile, dense=dense_profile, fusion=fusion_profile)
        with session_scope(factory) as session:
            session.execute(
                update(PolicyIndexVersionModel)
                .where(PolicyIndexVersionModel.index_name == INDEX_NAME)
                .values(
                    lexical_k1=lexical_profile.k1,
                    lexical_b=lexical_profile.b,
                    fusion_rrf_k=fusion_profile.rrf_k,
                    fusion_lexical_weight=fusion_profile.lexical_weight,
                    fusion_dense_weight=fusion_profile.dense_weight,
                )
            )
    else:
        lexical_profile, dense_profile, fusion_profile = load_profile()
        outcomes = evaluate_split(
            gold=gold,
            clause_repository=clauses,
            dense_retriever=dense_retriever,
            embedding_provider=provider,
            lexical_profile=lexical_profile,
            dense_profile=dense_profile,
            fusion_profile=fusion_profile,
        )
        profile_path = ROOT / "retrieval_profile_v1.json"
        profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
        if profile_payload.get("test_evaluated"):
            raise ValueError("locked test split was already evaluated")
        profile_payload["test_evaluated"] = True
        profile_payload["test_evaluated_at"] = datetime.now(UTC).isoformat()
        profile_path.write_text(
            json.dumps(profile_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    write_results(
        split=arguments.split,
        outcomes=outcomes,
        lexical=lexical_profile,
        dense=dense_profile,
        fusion=fusion_profile,
    )
    summary = {mode: metrics(outcomes, mode) for mode in outcomes[0].hits}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
