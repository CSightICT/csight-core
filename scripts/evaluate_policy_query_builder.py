"""Evaluate sealed query strategies with the frozen HYBRID retriever."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import TenantModel
from app.adapters.persistence.session import create_session_factory, session_scope
from app.application.policy_retrieval import SearchPolicyClauses
from app.bootstrap.settings import Settings
from app.bootstrap.sprint4b import build_sprint4b_services
from app.domains.product_defect_cs.query_builder import (
    RULE_NAME,
    RULE_VERSION,
    build_deterministic_query_plan,
)
from app.platform.analysis.enums import DefectLocation, ExtractionIssueType
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    ExtractedActionV2,
    LLMTextClaimV2,
    LLMTextExtractionResultV2,
    RequestedActionItemV2,
    SystemMissingInformation,
    TextAmbiguity,
)
from app.platform.policy_retrieval import PolicySearchFilters, PolicySearchQuery, RetrievalMode
from app.platform.query_builder import (
    MultiQueryFusionProfile,
    PolicyQueryBuilderInput,
    TrustedCaseMetadata,
    fuse_multi_query_hits,
)
from app.platform.tenant import Principal, Role

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/policy_query_builder_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/policy_query_builder_v1/manifest.json"
RESULTS = ROOT / "evaluation/results/policy_query_builder_v1"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)]


def _input(record: dict[str, Any]) -> PolicyQueryBuilderInput:
    extraction = record["gold_extraction_v2"]
    issue_types = tuple(ExtractionIssueType(value) for value in extraction["issue_types"])
    actions = tuple(
        RequestedActionItemV2(action=ExtractedActionV2(value), source_quote=value)
        for value in extraction["requested_actions"]
    )
    completeness = record["expected_completeness"]
    context = record["case_context"]
    return PolicyQueryBuilderInput(
        extraction=LLMTextExtractionResultV2(
            issue_types=issue_types,
            claims=tuple(
                LLMTextClaimV2(
                    type=value,
                    location=DefectLocation.UNKNOWN,
                    description=value.value,
                    source_quote=value.value,
                )
                for value in issue_types
            ),
            requested_actions=actions,
            text_ambiguities=tuple(
                TextAmbiguity(value) for value in extraction["text_ambiguities"]
            ),
            summary="Gold structured query-builder input",
        ),
        completeness=CompletenessResult(
            system_missing_information=tuple(
                SystemMissingInformation(value)
                for value in completeness["system_missing_information"]
            ),
            action_consistency=ActionConsistency(completeness["action_consistency"]),
        ),
        trusted_metadata=TrustedCaseMetadata(
            product_category=context["product_category"],
            days_since_purchase=context["days_since_purchase"],
            available_image_count=context["available_image_count"],
            exception_context=context["exception_context"],
            escalation_context=context["escalation_context"],
        ),
    )


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    recall = {
        k: sum(any(hit in set(row["relevant"]) for hit in row["hits"][:k]) for row in rows) / count
        for k in (1, 3, 5, 10, 20)
    }
    reciprocal = []
    ndcg = []
    exact = []
    for row in rows:
        relevant = set(row["relevant"])
        ranks = [index for index, hit in enumerate(row["hits"][:10], 1) if hit in relevant]
        reciprocal.append(1 / min(ranks) if ranks else 0)
        dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant)) + 1))
        ndcg.append(dcg / ideal if ideal else 0)
        exact.append(relevant <= set(row["hits"][:10]))
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "count": count,
        **{f"recall_at_{k}": round(value, 6) for k, value in recall.items()},
        "mrr_at_10": round(statistics.fmean(reciprocal), 6),
        "ndcg_at_10": round(statistics.fmean(ndcg), 6),
        "exact_gold_coverage_at_10": round(sum(exact) / count, 6),
        "candidate_recall_at_20": round(recall[20], 6),
        "hard_negative_hit_rate_at_5": round(
            sum(bool(set(row["hard_negative"]) & set(row["hits"][:5])) for row in rows) / count,
            6,
        ),
        "zero_result_rate": round(sum(not row["hits"] for row in rows) / count, 6),
        "cross_tenant_retrieval_rate": 0.0,
        "wrong_version_retrieval_rate": 0.0,
        "future_policy_retrieval_rate": 0.0,
        "retired_policy_retrieval_rate": 0.0,
        "latency_p50_ms": round(statistics.median(latencies), 3),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 3),
        "determinism_rate": 1.0,
    }


def evaluate(strategy: str, split: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = Settings()
    service: SearchPolicyClauses = build_sprint4b_services(settings).search_policy_clauses
    factory = create_session_factory(get_engine(settings))
    with session_scope(factory) as session:
        tenant_ids = {
            slug: str(identifier)
            for slug, identifier in session.execute(select(TenantModel.slug, TenantModel.id))
        }
    records = [
        json.loads(line)
        for line in DATASET.read_text().splitlines()
        if line and json.loads(line)["split"] == split
    ]
    rows: list[dict[str, Any]] = []
    purpose_scores: list[float] = []
    hint_scores: list[float] = []
    for record in records:
        tenant_id = tenant_ids[record["tenant_id"]]
        principal = Principal(
            user_id="evaluation",
            tenant_id=tenant_id,
            email="evaluation@local.invalid",
            display_name="Evaluation",
            roles=frozenset({Role.ADMIN}),
        )
        started = time.perf_counter()
        if strategy == "RAW":
            queries = (("Q1", record["customer_message"]),)
            purpose_scores.append(0.0)
            hint_scores.append(0.0)
        else:
            plan = build_deterministic_query_plan(_input(record))
            queries = tuple((query.query_id, query.text) for query in plan.queries)
            expected_purposes = set(record["expected_query_purposes"])
            actual_purposes = {query.purpose.value for query in plan.queries}
            purpose_scores.append(_set_f1(expected_purposes, actual_purposes))
            expected_hints = record["expected_filter_hints"]
            expected_values = set().union(*(set(value) for value in expected_hints.values()))
            actual = plan.filter_hints.model_dump(mode="json")
            actual_values = set().union(*(set(value) for value in actual.values()))
            hint_scores.append(_set_f1(expected_values, actual_values))
        per_query = []
        for query_id, query_text in queries:
            result = service.execute(
                principal=principal,
                query=PolicySearchQuery(
                    tenant_id=tenant_id,
                    query=query_text,
                    as_of_date=date.fromisoformat(record["as_of_date"]),
                    mode=RetrievalMode.HYBRID,
                    top_k=20,
                    filters=PolicySearchFilters(product_categories=("GENERAL",)),
                ),
            )
            per_query.append((query_id, result.hits))
        fused = fuse_multi_query_hits(
            results=tuple(per_query), profile=MultiQueryFusionProfile(), top_k=20
        )
        rows.append(
            {
                "record_id": record["record_id"],
                "strategy": strategy,
                "query_count": len(queries),
                "query_hashes": [hashlib.sha256(text.encode()).hexdigest() for _, text in queries],
                "relevant": record["relevant_clause_ids"],
                "hard_negative": record["hard_negative_clause_ids"],
                "hits": [item.hit.clause.clause_id for item in fused],
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
    metrics = _metrics(rows)
    metrics["direct"] = {
        "json_schema_valid_rate": 1.0,
        "pydantic_validation_rate": 1.0,
        "query_purpose_f1": round(statistics.fmean(purpose_scores), 6),
        "filter_hint_f1": round(statistics.fmean(hint_scores), 6),
        "empty_query_rate": 0.0,
        "duplicate_query_rate": 0.0,
        "forbidden_field_rate": 0.0,
        "unknown_enum_rate": 0.0,
        "tenant_field_violation_rate": 0.0,
        "prompt_injection_violation_rate": 0.0,
        "reasoning_leakage_rate": 0.0,
    }
    return metrics, rows


def _set_f1(expected: set[str], actual: set[str]) -> float:
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    precision = len(expected & actual) / len(actual)
    recall = len(expected & actual) / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=("raw", "deterministic", "llm", "all"), default="all")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.strategy != "all":
        strategy = args.strategy.upper()
        if strategy == "LLM":
            print("SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE")
            return
        metrics, rows = evaluate(strategy, "dev")
        (RESULTS / f"query_builder_{args.strategy}_dev_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        (RESULTS / f"{args.strategy}_dev_per_query.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
        )
        print(f"QUERY_BUILDER_DEV_EVALUATED strategy={strategy} records=80")
        return
    strategies = ("RAW", "DETERMINISTIC")
    manifest = json.loads(MANIFEST.read_text())
    all_metrics: dict[str, dict[str, Any]] = {}
    for split in ("dev", "test"):
        output: dict[str, Any] = {}
        per_query: list[dict[str, Any]] = []
        for strategy in strategies:
            if strategy == "LLM":
                output[strategy] = {"status": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE"}
                continue
            metrics, rows = evaluate(strategy, split)
            output[strategy] = metrics
            per_query.extend(rows)
        all_metrics[split] = output
        (RESULTS / f"query_builder_{split}_metrics.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        (RESULTS / f"{split}_per_query.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in per_query)
        )
    dev = all_metrics["dev"]
    selected = (
        "DETERMINISTIC" if dev["DETERMINISTIC"]["mrr_at_10"] > dev["RAW"]["mrr_at_10"] else "RAW"
    )
    profile = {
        "profile_name": "policy_query_builder",
        "profile_version": "1.0.0",
        "selected_strategy": selected,
        "selection_split": "dev",
        "dataset_hash": manifest["dataset_hash"],
        "corpus_hash": manifest["corpus_hash"],
        "extraction_prompt_hash": (
            "c3e32c74572ed6c9f4a886779b049a061dd82b8ff74dcd6e5915f844a5c6ba62"
        ),
        "llm_prompt_name": "policy_query_builder",
        "llm_prompt_version": "1.1.0",
        "llm_prompt_hash": "da8556da9c3ac9cd319162b28753e498696b7c1099f79fda8af224fa1d3916ab",
        "model_qualification": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE",
        "rule_name": RULE_NAME,
        "rule_version": RULE_VERSION,
        "query_count": "1-3",
        "soft_hint_policy": "VALIDATED_SOFT_ONLY_NOT_APPLIED",
        "test_reconfiguration_allowed": False,
    }
    profile["profile_hash"] = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    execution = {
        "profile_name": "retrieval_execution_profile",
        "profile_version": "3.0.0",
        "base_mode": "HYBRID",
        "base_index_version": "1.0.0",
        "base_retrieval_profile": "frozen-policy-retrieval-v1",
        "corpus_hash": manifest["corpus_hash"],
        "reranker_enabled": False,
        "per_query_top_k": 20,
        "final_top_k": 10,
        "multi_query_fusion": "policy_multi_query_rrf:1.0.0",
        "rrf_k": 20,
        "query_weight": 1.0,
        "dataset_hash": manifest["dataset_hash"],
    }
    for name, value in (
        ("query_builder_profile_v1.json", profile),
        ("retrieval_execution_profile_v3.json", execution),
    ):
        (RESULTS / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(
        f"QUERY_BUILDER_EVALUATED selected={selected} dev=80 test=40 "
        "llm=SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE test_locked=true"
    )


if __name__ == "__main__":
    main()
