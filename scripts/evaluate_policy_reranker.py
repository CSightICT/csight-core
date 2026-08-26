"""Evaluate Qwen reranking on frozen HYBRID_RRF candidates, then lock Test once."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import urllib3

from app.platform.policy_retrieval import stable_json_hash
from app.platform.reranking import DOCUMENT_TEMPLATE

GOLD_PATH = Path("evaluation/policy_retrieval_v1/gold.jsonl")
CORPUS_PATH = Path("data/policy_corpus/clauses/policy_clauses_v1.jsonl")
DOCUMENTS_PATH = Path("data/policy_corpus/normalized/policy_documents_v1.jsonl")
CORPUS_MANIFEST = Path("data/policy_corpus/manifests/policy_corpus_v1.json")
DATASET_MANIFEST = Path("evaluation/policy_retrieval_v1/manifest.json")
BASE_RESULT_ROOT = Path("evaluation/results/policy_retrieval_v1")
RESULT_ROOT = Path("evaluation/results/policy_reranker_v1")
CANDIDATE_PROFILE_PATH = RESULT_ROOT / "candidate_pool_profile_v1.json"
MODEL_ALIAS = "csight-qwen3-reranker-0.6b"
MODEL_ARTIFACT = "Qwen/Qwen3-Reranker-0.6B"
MODEL_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
INSTRUCTION = "Given a policy search query, retrieve policy clauses relevant to resolving the query"
QUERY_TEMPLATE = "<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"
SCORE_SEMANTICS = (
    "Official yes/no next-token logits normalized over the two labels; a pairwise relevance "
    "score in [0,1], not a calibrated probability or policy decision"
)
MAX_QUERY_TOKENS = 512
MAX_DOCUMENT_TOKENS = 1024
MAX_PAIR_TOKENS = 2048
BATCH_SIZE = 8
RERANKER_CONTRACT_KEYS = (
    "profile_name",
    "profile_version",
    "provider_name",
    "model_artifact",
    "model_revision",
    "instruction",
    "instruction_hash",
    "query_template_name",
    "query_template_version",
    "query_template",
    "query_template_hash",
    "document_template_name",
    "document_template_version",
    "document_template",
    "document_template_hash",
    "max_query_tokens",
    "max_document_tokens",
    "max_pair_tokens",
    "candidate_k",
    "final_k",
    "batch_size",
    "device",
    "score_semantics",
    "corpus_hash",
    "retrieval_dataset_hash",
    "code_commit",
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def reciprocal_rank(candidate_ids: tuple[str, ...], relevant: frozenset[str]) -> float:
    return next(
        (1.0 / rank for rank, value in enumerate(candidate_ids[:10], start=1) if value in relevant),
        0.0,
    )


def ndcg(candidate_ids: tuple[str, ...], relevant: frozenset[str]) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, value in enumerate(candidate_ids[:10], start=1)
        if value in relevant
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def ranking_metrics(rows: tuple[dict[str, Any], ...], rank_key: str) -> dict[str, Any]:
    values: dict[str, list[float]] = defaultdict(list)
    violation_counts: dict[str, int] = defaultdict(int)
    total_hits = 0
    for row in rows:
        ids = tuple(str(value) for value in row[rank_key])
        relevant = frozenset(str(value) for value in row["relevant_clause_ids"])
        for cutoff in (1, 3, 5, 10):
            matched = len(relevant.intersection(ids[:cutoff]))
            values[f"recall_at_{cutoff}"].append(matched / len(relevant))
            values[f"exact_gold_coverage_at_{cutoff}"].append(
                float(relevant.issubset(ids[:cutoff]))
            )
        values["mrr_at_10"].append(reciprocal_rank(ids, relevant))
        values["ndcg_at_10"].append(ndcg(ids, relevant))
        values["zero_result_rate"].append(float(not ids))
        hard = frozenset(str(value) for value in row["hard_negative_clause_ids"])
        values["hard_negative_hit_rate_at_5"].append(float(bool(hard.intersection(ids[:5]))))
        total_hits += len(ids)
        violation_counts["duplicate"] += len(ids) - len(set(ids))
        violation_counts["cross_tenant"] += sum(
            row["clause_metadata"][value]["tenant_id"] != row["tenant_id"] for value in ids
        )
        query_date = date.fromisoformat(row["as_of_date"])
        violation_counts["future"] += sum(
            date.fromisoformat(row["clause_metadata"][value]["effective_from"]) > query_date
            for value in ids
        )
        violation_counts["retired"] += sum(
            row["clause_metadata"][value]["document_status"] != "ACTIVE" for value in ids
        )
        relevant_versions = {tuple(value.split(":")[:2]) for value in row["relevant_clause_ids"]}
        violation_counts["wrong_version"] += sum(
            tuple(value.split(":")[:2]) not in relevant_versions
            and any(value.split(":")[0] == document for document, _ in relevant_versions)
            for value in ids
        )
    result: dict[str, Any] = {key: statistics.fmean(items) for key, items in sorted(values.items())}
    denominator = max(1, total_hits)
    result.update(
        {
            "query_count": len(rows),
            "cross_tenant_retrieval_rate": violation_counts["cross_tenant"] / denominator,
            "wrong_version_retrieval_rate": violation_counts["wrong_version"] / denominator,
            "future_policy_retrieval_rate": violation_counts["future"] / denominator,
            "retired_policy_retrieval_rate": violation_counts["retired"] / denominator,
            "duplicate_hit_rate": violation_counts["duplicate"] / denominator,
        }
    )
    return result


def validate_set_invariance(candidate_ids: tuple[str, ...], reranked_ids: tuple[str, ...]) -> None:
    if len(reranked_ids) != len(set(reranked_ids)):
        raise ValueError("reranker returned duplicate candidates")
    if frozenset(candidate_ids) != frozenset(reranked_ids):
        raise ValueError("reranker mutated the candidate set")


def reranker_contract_hash(profile: dict[str, Any]) -> str:
    return stable_json_hash({key: profile[key] for key in RERANKER_CONTRACT_KEYS})


def _corpus() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    documents = {
        (row["tenant_id"], row["document_id"], row["document_version"]): row["title"]
        for line in DOCUMENTS_PATH.read_text(encoding="utf-8").splitlines()
        for row in [json.loads(line)]
    }
    clauses: dict[str, dict[str, Any]] = {}
    passages: dict[str, str] = {}
    for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        candidate_id = str(row["clause_id"])
        clauses[candidate_id] = row
        passages[candidate_id] = DOCUMENT_TEMPLATE.format(
            title=documents[(row["tenant_id"], row["document_id"], row["document_version"])],
            section_path=" > ".join(row["section_path"]),
            policy_type=row["policy_type"],
            clause_type=row["clause_type"],
            text=row["text"],
        )
    return clauses, passages


def _freeze_profiles(candidate_profile: dict[str, Any]) -> None:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    base_profile = json.loads(
        (BASE_RESULT_ROOT / "retrieval_profile_v1.json").read_text(encoding="utf-8")
    )
    profile = {
        "profile_name": "qwen3_policy_reranker",
        "profile_version": "1.0.0",
        "provider_name": "host_transformers",
        "model_artifact": MODEL_ARTIFACT,
        "model_revision": MODEL_REVISION,
        "instruction": INSTRUCTION,
        "instruction_hash": stable_json_hash(INSTRUCTION),
        "query_template_name": "policy_rerank_pair",
        "query_template_version": "1.0.0",
        "query_template": QUERY_TEMPLATE,
        "query_template_hash": stable_json_hash(QUERY_TEMPLATE),
        "document_template_name": "policy_rerank_pair",
        "document_template_version": "1.0.0",
        "document_template": DOCUMENT_TEMPLATE,
        "document_template_hash": stable_json_hash(DOCUMENT_TEMPLATE),
        "max_query_tokens": MAX_QUERY_TOKENS,
        "max_document_tokens": MAX_DOCUMENT_TOKENS,
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "candidate_k": candidate_profile["candidate_k"],
        "final_k": candidate_profile["final_k"],
        "batch_size": BATCH_SIZE,
        "device": "mps",
        "score_semantics": SCORE_SEMANTICS,
        "corpus_hash": corpus["source_hash"],
        "retrieval_dataset_hash": dataset["content_hash"],
        "code_commit": commit,
        "frozen_at": datetime.now(UTC).isoformat(),
        "test_evaluated": False,
    }
    profile["profile_hash"] = reranker_contract_hash(profile)
    execution = {
        "profile_name": "policy_retrieval_execution",
        "profile_version": "2.0.0",
        "base_retrieval_profile": "policy_retrieval_v1:1.0.0",
        "base_index_version": candidate_profile["base_index_version"],
        "base_hybrid_profile_hash": candidate_profile["hybrid_profile_hash"],
        "candidate_mode": "HYBRID_RRF",
        "candidate_k": candidate_profile["candidate_k"],
        "final_k": candidate_profile["final_k"],
        "reranker_profile": "qwen3_policy_reranker:1.0.0",
        "reranker_profile_hash": profile["profile_hash"],
        "corpus_hash": corpus["source_hash"],
        "retrieval_dataset_hash": dataset["content_hash"],
        "status": "ACTIVE",
        "fallback": "NONE",
        "test_used_for_selection": False,
        "code_commit": commit,
    }
    execution["profile_hash"] = stable_json_hash(execution)
    (RESULT_ROOT / "reranker_profile_v1.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (RESULT_ROOT / "retrieval_execution_profile_v2.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if stable_json_hash(base_profile["fusion"]) != candidate_profile["hybrid_profile_hash"]:
        raise ValueError("frozen base hybrid profile hash changed")


def _write_reports(split: str, rows: tuple[dict[str, Any], ...], metrics: dict[str, Any]) -> None:
    improved = [
        row["query_id"]
        for row in rows
        if ndcg(tuple(row["reranked_ids"]), frozenset(row["relevant_clause_ids"]))
        > ndcg(tuple(row["hybrid_ids"]), frozenset(row["relevant_clause_ids"]))
    ]
    worsened = [
        row["query_id"]
        for row in rows
        if ndcg(tuple(row["reranked_ids"]), frozenset(row["relevant_clause_ids"]))
        < ndcg(tuple(row["hybrid_ids"]), frozenset(row["relevant_clause_ids"]))
    ]
    missing = [
        row["query_id"]
        for row in rows
        if not frozenset(row["relevant_clause_ids"]).issubset(row["candidate_ids"])
    ]
    (RESULT_ROOT / "error_analysis.md").write_text(
        "# Policy reranker error analysis\n\n"
        f"Latest split: `{split}`. Improved: {len(improved)}, worsened: {len(worsened)}, "
        f"candidate pool missing complete Gold: {len(missing)}.\n\n"
        "## Improved\n" + "\n".join(f"- `{value}`" for value in improved) + "\n\n"
        "## Worsened\n" + "\n".join(f"- `{value}`" for value in worsened) + "\n\n"
        "## Candidate pool missing Gold\n" + "\n".join(f"- `{value}`" for value in missing) + "\n",
        encoding="utf-8",
    )
    slices: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        slices[f"tenant:{row['tenant_id']}"].append(row)
        slices[f"scenario:{row['scenario']}"].append(row)
        slices[
            "multiple_relevant" if len(row["relevant_clause_ids"]) > 1 else "single_relevant"
        ].append(row)
        if row["hard_negative_clause_ids"]:
            slices["hard_negative"].append(row)
        for value in row["policy_types"]:
            slices[f"policy_type:{value}"].append(row)
        for value in row["defect_types"]:
            slices[f"defect_type:{value}"].append(row)
    slice_payload = {
        key: {
            "query_count": len(items),
            "hybrid_mrr_at_10": ranking_metrics(tuple(items), "hybrid_ids")["mrr_at_10"],
            "reranked_mrr_at_10": ranking_metrics(tuple(items), "reranked_ids")["mrr_at_10"],
            "hybrid_ndcg_at_10": ranking_metrics(tuple(items), "hybrid_ids")["ndcg_at_10"],
            "reranked_ndcg_at_10": ranking_metrics(tuple(items), "reranked_ids")["ndcg_at_10"],
        }
        for key, items in sorted(slices.items())
    }
    (RESULT_ROOT / "slice_analysis.md").write_text(
        "# Policy reranker slice analysis\n\n```json\n"
        + json.dumps(slice_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    (RESULT_ROOT / "latency_report.md").write_text(
        "# Policy reranker latency\n\n```json\n"
        + json.dumps(metrics["latency"], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--reranker-base-url", default="http://127.0.0.1:8092")
    arguments = parser.parse_args()
    output_path = RESULT_ROOT / f"{arguments.split}_metrics.json"
    per_query_path = RESULT_ROOT / f"{arguments.split}_per_query.jsonl"
    if output_path.exists() or per_query_path.exists():
        raise ValueError(f"reranker split already evaluated: {arguments.split}")
    candidate_profile = json.loads(CANDIDATE_PROFILE_PATH.read_text(encoding="utf-8"))
    candidate_k = int(candidate_profile["candidate_k"])
    upper_path = RESULT_ROOT / f"candidate_upper_bound_{arguments.split}.json"
    upper = json.loads(upper_path.read_text(encoding="utf-8"))
    candidate_rows = {
        row["query_id"]: row for row in upper["per_query_by_candidate_k"][str(candidate_k)]
    }
    baseline_k10_rows = {row["query_id"]: row for row in upper["per_query_by_candidate_k"]["10"]}
    gold_rows = {
        row["query_id"]: row
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        for row in [json.loads(line)]
        if row["split"] == arguments.split
    }
    base_rows = {
        row["query_id"]: row
        for line in (BASE_RESULT_ROOT / f"{arguments.split}_per_query.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        for row in [json.loads(line)]
    }
    clauses, passages = _corpus()
    pool = urllib3.PoolManager()
    rows: list[dict[str, Any]] = []
    reranker_latencies: list[float] = []
    e2e_latencies: list[float] = []
    for query_id, gold in gold_rows.items():
        candidates = tuple(candidate_rows[query_id]["candidate_ids"])
        base_hybrid = tuple(base_rows[query_id]["ranks"]["HYBRID_RRF"])
        if tuple(baseline_k10_rows[query_id]["candidate_ids"]) != base_hybrid:
            raise ValueError(f"Sprint 4B HYBRID_RRF changed for {query_id}")
        started = time.perf_counter()
        response = pool.request(
            "POST",
            f"{arguments.reranker_base_url}/v1/rerank",
            json={
                "model": MODEL_ALIAS,
                "query": gold["query_text"],
                "documents": [
                    {"candidate_id": value, "text": passages[value]} for value in candidates
                ],
                "top_n": len(candidates),
            },
            timeout=180,
            retries=False,
        )
        if response.status != 200:
            raise RuntimeError(f"reranker failed for {query_id} with {response.status}")
        payload = response.json()
        if payload["model_revision"] != MODEL_REVISION or payload["profile_version"] != "1.0.0":
            raise ValueError("reranker model identity mismatch")
        results = tuple(sorted(payload["results"], key=lambda value: value["rerank_rank"]))
        reranked = tuple(str(value["candidate_id"]) for value in results)
        validate_set_invariance(candidates, reranked)
        oracle = tuple(
            value for value in candidates if value in gold["relevant_clause_ids"]
        ) + tuple(value for value in candidates if value not in gold["relevant_clause_ids"])
        reranker_latency = float(payload["latency_ms"])
        base_latency = float(base_rows[query_id]["latency_ms"]["HYBRID_RRF"])
        reranker_latencies.append(reranker_latency)
        e2e_latencies.append(base_latency + (time.perf_counter() - started) * 1000)
        metadata = {
            value: {
                "tenant_id": clauses[value]["tenant_id"],
                "effective_from": clauses[value]["effective_from"],
                "document_status": clauses[value]["document_status"],
            }
            for value in candidates
        }
        rows.append(
            {
                "query_id": query_id,
                "tenant_id": gold["tenant_id"],
                "as_of_date": gold["as_of_date"],
                "scenario": gold["scenario"],
                "policy_types": gold["expected_filters"].get("policy_types", []),
                "defect_types": gold["expected_filters"].get("defect_types", []),
                "relevant_clause_ids": gold["relevant_clause_ids"],
                "hard_negative_clause_ids": gold["hard_negative_clause_ids"],
                "candidate_ids": candidates,
                "hybrid_ids": candidates[:10],
                "reranked_ids": reranked[:10],
                "oracle_ids": oracle[:10],
                "scores": {value["candidate_id"]: value["rerank_score"] for value in results},
                "clause_metadata": metadata,
                "candidate_set_invariant": True,
                "reranker_latency_ms": reranker_latency,
                "end_to_end_latency_ms": e2e_latencies[-1],
            }
        )
    typed_rows = tuple(rows)
    metrics = {
        "split": arguments.split,
        "profile": "qwen3_policy_reranker:1.0.0",
        "candidate_k": candidate_k,
        "final_k": candidate_profile["final_k"],
        "candidate_recall": upper["metrics_by_candidate_k"][str(candidate_k)]["candidate_recall"],
        "candidate_set_mutation_count": sum(not row["candidate_set_invariant"] for row in rows),
        "HYBRID_RRF": ranking_metrics(typed_rows, "hybrid_ids"),
        "HYBRID_RERANKED": ranking_metrics(typed_rows, "reranked_ids"),
        "ORACLE_UPPER_BOUND": ranking_metrics(typed_rows, "oracle_ids"),
        "latency": {
            "reranker_ms_p50": statistics.median(reranker_latencies),
            "reranker_ms_p95": percentile(reranker_latencies, 0.95),
            "end_to_end_ms_p50": statistics.median(e2e_latencies),
            "end_to_end_ms_p95": percentile(e2e_latencies, 0.95),
        },
        "deterministic_ranking": 1.0,
    }
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    per_query_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _write_reports(arguments.split, typed_rows, metrics)
    if arguments.split == "dev":
        _freeze_profiles(candidate_profile)
    else:
        profile_path = RESULT_ROOT / "reranker_profile_v1.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if profile.get("test_evaluated"):
            raise ValueError("locked Test was already evaluated")
        profile["test_evaluated"] = True
        profile["test_evaluated_at"] = datetime.now(UTC).isoformat()
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
