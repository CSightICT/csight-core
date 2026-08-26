"""Verify locked reranker artifacts; optionally rerun only Dev for determinism."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import urllib3

from app.platform.policy_retrieval import stable_json_hash
from scripts.evaluate_policy_reranker import (
    MODEL_ALIAS,
    RESULT_ROOT,
    _corpus,
    reranker_contract_hash,
    validate_set_invariance,
)

GOLD_PATH = Path("evaluation/policy_retrieval_v1/gold.jsonl")
REQUIRED_FILES = (
    "reranker_profile_v1.json",
    "retrieval_execution_profile_v2.json",
    "candidate_upper_bound_dev.json",
    "candidate_upper_bound_test.json",
    "dev_metrics.json",
    "test_metrics.json",
    "dev_per_query.jsonl",
    "test_per_query.jsonl",
    "error_analysis.md",
    "slice_analysis.md",
    "latency_report.md",
    "reranker_qualification_report.md",
)


def _rows(split: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for line in (RESULT_ROOT / f"{split}_per_query.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerun-dev", action="store_true")
    parser.add_argument("--reranker-base-url", default="http://127.0.0.1:8092")
    arguments = parser.parse_args()
    missing = [value for value in REQUIRED_FILES if not (RESULT_ROOT / value).exists()]
    if missing:
        raise ValueError(f"missing reranker artifacts: {missing}")
    profile = json.loads((RESULT_ROOT / "reranker_profile_v1.json").read_text(encoding="utf-8"))
    execution = json.loads(
        (RESULT_ROOT / "retrieval_execution_profile_v2.json").read_text(encoding="utf-8")
    )
    if (
        not profile.get("test_evaluated")
        or reranker_contract_hash(profile) != profile["profile_hash"]
    ):
        raise ValueError("reranker profile is not locked or its contract hash changed")
    execution_contract = {key: value for key, value in execution.items() if key != "profile_hash"}
    if stable_json_hash(execution_contract) != execution["profile_hash"]:
        raise ValueError("execution profile hash changed")
    for split, expected in (("dev", 80), ("test", 40)):
        rows = _rows(split)
        if len(rows) != expected:
            raise ValueError(f"{split} query count changed")
        for row in rows:
            validate_set_invariance(tuple(row["candidate_ids"]), tuple(row["scores"]))
            if not row["candidate_set_invariant"]:
                raise ValueError("candidate set invariant is false")
        metrics = json.loads((RESULT_ROOT / f"{split}_metrics.json").read_text(encoding="utf-8"))
        for mode in ("HYBRID_RRF", "HYBRID_RERANKED", "ORACLE_UPPER_BOUND"):
            values = metrics[mode]
            if any(
                values[key] != 0
                for key in (
                    "cross_tenant_retrieval_rate",
                    "wrong_version_retrieval_rate",
                    "future_policy_retrieval_rate",
                    "retired_policy_retrieval_rate",
                    "duplicate_hit_rate",
                )
            ):
                raise ValueError(f"{split} {mode} correctness violation")
    rerun_count = 0
    if arguments.rerun_dev:
        gold = {
            row["query_id"]: row
            for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
            for row in [json.loads(line)]
            if row["split"] == "dev"
        }
        _, passages = _corpus()
        pool = urllib3.PoolManager()
        for row in _rows("dev"):
            response = pool.request(
                "POST",
                f"{arguments.reranker_base_url}/v1/rerank",
                json={
                    "model": MODEL_ALIAS,
                    "query": gold[row["query_id"]]["query_text"],
                    "documents": [
                        {"candidate_id": value, "text": passages[value]}
                        for value in row["candidate_ids"]
                    ],
                    "top_n": len(row["candidate_ids"]),
                },
                timeout=180,
                retries=False,
            )
            if response.status != 200:
                raise RuntimeError("Dev deterministic rerun provider failure")
            reranked = tuple(
                value["candidate_id"]
                for value in sorted(
                    response.json()["results"], key=lambda value: value["rerank_rank"]
                )
            )
            validate_set_invariance(tuple(row["candidate_ids"]), reranked)
            if reranked[:10] != tuple(row["reranked_ids"]):
                raise ValueError(f"non-deterministic rerank for {row['query_id']}")
            rerun_count += 1
    print(
        "POLICY_RERANKER_RESULTS_VERIFIED "
        f"dev=80 test=40 test_locked=true candidate_mutation=0 dev_rerun={rerun_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
