"""Measure the pinned private reranker service without logging model inputs."""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import torch
import transformers
from transformers import AutoTokenizer

from infra.reranker.server import (
    MAX_BATCH_SIZE,
    MAX_PAIR_TOKENS,
    MODEL_ALIAS,
    MODEL_ARTIFACT,
    MODEL_REVISION,
    PREFIX,
    SUFFIX,
    Runtime,
)

RESULT_ROOT = Path("evaluation/results/policy_reranker_v1")
GOLD_PATH = Path("evaluation/policy_retrieval_v1/gold.jsonl")
CLAUSE_PATH = Path("data/policy_corpus/clauses/policy_clauses_v1.jsonl")
DOCUMENT_PATH = Path("data/policy_corpus/normalized/policy_documents_v1.jsonl")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _host_value(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, encoding="utf-8").strip()


def _passages() -> list[tuple[str, str]]:
    documents = {
        (row["tenant_id"], row["document_id"], row["document_version"]): row["title"]
        for line in DOCUMENT_PATH.read_text(encoding="utf-8").splitlines()
        for row in [json.loads(line)]
    }
    return [
        (
            row["clause_id"],
            "\n".join(
                (
                    "문서: "
                    + documents[(row["tenant_id"], row["document_id"], row["document_version"])],
                    f"섹션: {' > '.join(row['section_path'])}",
                    f"정책 유형: {row['policy_type']}",
                    f"조항 유형: {row['clause_type']}",
                    f"본문: {row['text']}",
                )
            ),
        )
        for line in CLAUSE_PATH.read_text(encoding="utf-8").splitlines()
        for row in [json.loads(line)]
    ]


def _request(base_url: str, query: str, documents: list[tuple[str, str]]) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=300) as client:
        response = client.post(
            "/v1/rerank",
            json={
                "model": MODEL_ALIAS,
                "query": query,
                "documents": [
                    {"candidate_id": candidate_id, "text": text} for candidate_id, text in documents
                ],
                "top_n": len(documents),
            },
        )
        response.raise_for_status()
        return dict(response.json())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8092")
    parser.add_argument("--model-download-seconds", type=float, required=True)
    parser.add_argument("--cached-cold-load-seconds", type=float, required=True)
    arguments = parser.parse_args()
    passages = _passages()
    queries = [
        row
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        for row in [json.loads(line)]
    ]
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ARTIFACT,
        revision=MODEL_REVISION,
        padding_side="left",
        trust_remote_code=False,
    )
    prefix_count = len(tokenizer.encode(PREFIX, add_special_tokens=False))
    suffix_count = len(tokenizer.encode(SUFFIX, add_special_tokens=False))
    pair_counts: list[int] = []
    truncated_query_ids: set[str] = set()
    truncated_clause_ids: set[str] = set()
    passage_by_id = dict(passages)
    candidate_profile = json.loads(
        (RESULT_ROOT / "candidate_pool_profile_v1.json").read_text(encoding="utf-8")
    )
    candidate_k = str(candidate_profile["candidate_k"])
    for split in ("dev", "test"):
        upper = json.loads(
            (RESULT_ROOT / f"candidate_upper_bound_{split}.json").read_text(encoding="utf-8")
        )
        gold = {row["query_id"]: row for row in queries if row["split"] == split}
        for row in upper["per_query_by_candidate_k"][candidate_k]:
            query = gold[row["query_id"]]["query_text"]
            for candidate_id in row["candidate_ids"]:
                pair = Runtime.pair_text(query, passage_by_id[candidate_id])
                count = (
                    prefix_count
                    + len(tokenizer.encode(pair, add_special_tokens=False))
                    + suffix_count
                )
                pair_counts.append(count)
                if count > MAX_PAIR_TOKENS:
                    truncated_query_ids.add(row["query_id"])
                    truncated_clause_ids.add(candidate_id)

    query = "수령 후 3일 내 누액 상품의 교환 조건과 필요한 이미지 증거"
    warm_started = time.perf_counter()
    warm = _request(arguments.base_url, query, passages[:2])
    warm_ms = (time.perf_counter() - warm_started) * 1000
    single_latencies: list[float] = []
    for _ in range(10):
        started = time.perf_counter()
        _request(arguments.base_url, query, passages[:1])
        single_latencies.append((time.perf_counter() - started) * 1000)
    candidate_latency: dict[str, dict[str, float]] = {}
    for size in (10, 20, 30, 50):
        latencies: list[float] = []
        for _ in range(3):
            started = time.perf_counter()
            _request(arguments.base_url, query, passages[:size])
            latencies.append((time.perf_counter() - started) * 1000)
        candidate_latency[str(size)] = {
            "p50_ms": statistics.median(latencies),
            "p95_ms": percentile(latencies, 0.95),
        }

    started = time.perf_counter()
    _request(arguments.base_url, query, passages[:10])
    concurrency_one_wall = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent = tuple(
            executor.map(
                lambda _: _request(arguments.base_url, query, passages[:10]),
                range(2),
            )
        )
    concurrency_two_wall = (time.perf_counter() - started) * 1000
    with httpx.Client(base_url=arguments.base_url, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        models = client.get("/v1/models")
        models.raise_for_status()
    report = {
        "qualification": "QWEN3_RERANKER_QUALIFIED_WITH_LIMITATIONS",
        "limitations": [
            "Synthetic policy corpus and queries only",
            "Concurrency 2 is serialized by the model lock",
            "Dev/Test ranking quality shows no measurable gain over HYBRID_RRF",
        ],
        "environment": {
            "mac_model": _host_value(["sysctl", "-n", "hw.model"]),
            "unified_memory_bytes": int(_host_value(["sysctl", "-n", "hw.memsize"])),
            "macos": _host_value(["sw_vers", "-productVersion"]),
            "python": platform.python_version(),
            "pytorch": torch.__version__,
            "transformers": transformers.__version__,
            "device": "mps",
        },
        "model": models.json()["data"][0],
        "model_download_seconds": arguments.model_download_seconds,
        "cached_cold_load_seconds": arguments.cached_cold_load_seconds,
        "warmup_ms": warm_ms,
        "memory": health.json(),
        "token_report": {
            "minimum": min(pair_counts),
            "p50": statistics.median(pair_counts),
            "p95": percentile(pair_counts, 0.95),
            "maximum": max(pair_counts),
            "truncation_count": len(truncated_clause_ids),
            "truncated_query_ids": sorted(truncated_query_ids),
            "truncated_clause_ids": sorted(truncated_clause_ids),
            "policy": "reject pair above versioned max_pair_tokens; no silent truncation",
        },
        "performance": {
            "pair_score_p50_ms": statistics.median(single_latencies),
            "pair_score_p95_ms": percentile(single_latencies, 0.95),
            "candidate_latency": candidate_latency,
            "configured_batch_size": MAX_BATCH_SIZE,
            "concurrency_1_candidate_10_wall_ms": concurrency_one_wall,
            "concurrency_2_two_candidate_10_wall_ms": concurrency_two_wall,
            "concurrency_2_provider_latency_ms": [
                float(value["latency_ms"]) for value in concurrent
            ],
            "concurrency_limit": 1,
        },
        "sample_scores": [
            {
                "candidate_id": value["candidate_id"],
                "rerank_score": value["rerank_score"],
            }
            for value in warm["results"]
        ],
    }
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    (RESULT_ROOT / "reranker_qualification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (RESULT_ROOT / "reranker_qualification_report.md").write_text(
        "# Qwen3 policy reranker qualification\n\n"
        f"Qualification: `{report['qualification']}`. Artifact `{MODEL_ARTIFACT}` at revision "
        f"`{MODEL_REVISION}` ran on MPS. Pair tokens min/p50/p95/max are "
        f"{min(pair_counts)}/{statistics.median(pair_counts)}/{percentile(pair_counts, 0.95)}/"
        f"{max(pair_counts)} with {len(truncated_clause_ids)} truncations.\n\n"
        "The score is the official normalized yes-vs-no pairwise relevance score. It is not a "
        "calibrated probability, policy applicability, approval, or business-decision score.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
