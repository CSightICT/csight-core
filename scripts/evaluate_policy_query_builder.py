"""Evaluate Dev query strategies; historical sealed Test and profiles stay read-only."""

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
from scripts.evaluation_reporting import (
    private_observation_summary,
    ranking_metrics_from_rows,
    reserve_new_output,
    unmeasured_metrics,
    write_json_new,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/policy_query_builder_v1/gold.jsonl"


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
    ranking = ranking_metrics_from_rows(rows)
    count = len(rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "count": count,
        **ranking,
        "hard_negative_hit_rate_at_5": round(
            sum(bool(set(row["hard_negative"]) & set(row["hits"][:5])) for row in rows) / count,
            6,
        ),
        "zero_result_rate": round(sum(not row["hits"] for row in rows) / count, 6),
        **unmeasured_metrics(
            "cross_tenant_retrieval_rate",
            "wrong_version_retrieval_rate",
            "future_policy_retrieval_rate",
            "retired_policy_retrieval_rate",
            "determinism_rate",
        ),
        "latency_p50_ms": round(statistics.median(latencies), 3),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 3),
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
        **unmeasured_metrics(
            "json_schema_valid_rate",
            "pydantic_validation_rate",
            "empty_query_rate",
            "duplicate_query_rate",
            "forbidden_field_rate",
            "unknown_enum_rate",
            "tenant_field_violation_rate",
            "prompt_injection_violation_rate",
            "reasoning_leakage_rate",
        ),
        "query_purpose_f1": round(statistics.fmean(purpose_scores), 6),
        "filter_hint_f1": round(statistics.fmean(hint_scores), 6),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("raw", "deterministic", "llm", "all"), default="all")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument(
        "--output-dir", type=Path, help="New private run directory; parent must exist"
    )
    args = parser.parse_args()
    if args.split != "dev":
        print(json.dumps({"status": "BLOCKED", "error": "LEGACY_SEALED_TEST_DISABLED"}))
        return 2
    if args.strategy == "llm":
        print(json.dumps({"status": "SKIPPED", "reason": "EXTERNAL_LLM_NOT_AVAILABLE"}))
        return 0
    try:
        output_directory = reserve_new_output(args.output_dir)
    except (ValueError, OSError):
        print(json.dumps({"status": "FAIL", "error": "NEW_OUTPUT_DIRECTORY_REQUIRED"}))
        return 2
    strategies = ("RAW", "DETERMINISTIC") if args.strategy == "all" else (args.strategy.upper(),)
    try:
        output: dict[str, Any] = {}
        observations: dict[str, Any] = {}
        for strategy in strategies:
            metrics, rows = evaluate(strategy, "dev")
            output[strategy] = metrics
            observations[strategy] = private_observation_summary(rows)
        digest = write_json_new(
            output_directory / "result.json",
            {
                "schema_version": "query_builder_dev_evaluation/2.0.0",
                "split": "dev",
                "metrics": output,
                "observations": observations,
                "release_eligible": False,
                "profile_frozen": False,
                "default_strategy_changed": False,
            },
        )
    except Exception:
        # Boundary errors can include URLs, credentials or provider/customer content.
        print(json.dumps({"status": "FAIL", "error": "DEV_EVALUATION_FAILED"}))
        return 2
    print(json.dumps({"status": "PASS", "split": "dev", "report_sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
