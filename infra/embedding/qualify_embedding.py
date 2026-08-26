"""Measure the running private embedding service without logging raw vectors."""

import argparse
import json
import math
import os
import statistics
import time
from pathlib import Path

import httpx
import sentence_transformers
import torch
import transformers


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/policy_retrieval_v1/embedding_qualification.json"),
    )
    parser.add_argument("--model-download-seconds", type=float, required=True)
    parser.add_argument("--cached-cold-load-seconds", type=float, required=True)
    parser.add_argument("--peak-memory-bytes", type=int, required=True)
    arguments = parser.parse_args()
    base_url = os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:8091")
    documents = {
        (value["tenant_id"], value["document_id"], value["document_version"]): value["title"]
        for line in Path("data/policy_corpus/normalized/policy_documents_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        for value in [json.loads(line)]
    }
    clause_records = [
        json.loads(line)
        for line in Path("data/policy_corpus/clauses/policy_clauses_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    clauses = [
        "\n".join(
            (
                "문서: "
                + documents[(value["tenant_id"], value["document_id"], value["document_version"])],
                f"섹션: {' > '.join(value['section_path'])}",
                f"정책 유형: {value['policy_type']}",
                f"조항 유형: {value['clause_type']}",
                f"본문: {value['text']}",
            )
        )
        for value in clause_records
    ]
    with httpx.Client(base_url=base_url, timeout=120) as client:
        health = client.get("/health")
        health.raise_for_status()
        models = client.get("/v1/models")
        models.raise_for_status()
        started = time.perf_counter()
        embedded_items: list[dict[str, object]] = []
        for offset in range(0, len(clauses), 16):
            response = client.post(
                "/v1/embeddings",
                json={
                    "model": "csight-qwen3-embedding-0.6b",
                    "input": clauses[offset : offset + 16],
                    "input_type": "document",
                },
            )
            response.raise_for_status()
            embedded_items.extend(response.json()["data"])
        clause_seconds = time.perf_counter() - started
        query_latencies: list[float] = []
        for _ in range(10):
            started = time.perf_counter()
            query = client.post(
                "/v1/embeddings",
                json={
                    "model": "csight-qwen3-embedding-0.6b",
                    "input": ["누액 상품의 교환 조건과 필요한 이미지 증거"],
                    "input_type": "query",
                },
            )
            query.raise_for_status()
            query_latencies.append((time.perf_counter() - started) * 1000)
    token_counts = [int(item["token_count"]) for item in embedded_items]
    report = {
        "qualification": "QWEN3_EMBEDDING_QUALIFIED",
        "runtime": {
            "python": os.sys.version.split()[0],
            "pytorch": torch.__version__,
            "sentence_transformers": sentence_transformers.__version__,
            "transformers": transformers.__version__,
            "device": "mps",
        },
        "health": health.json(),
        "model": models.json()["data"][0],
        "clause_count": len(clauses),
        "clause_embedding_seconds": clause_seconds,
        "batch_size": len(clauses),
        "request_batch_size": 16,
        "model_download_seconds": arguments.model_download_seconds,
        "cached_cold_load_seconds": arguments.cached_cold_load_seconds,
        "peak_memory_bytes": arguments.peak_memory_bytes,
        "token_count": {
            "minimum": min(token_counts),
            "p50": statistics.median(token_counts),
            "p95": percentile(token_counts, 0.95),
            "maximum": max(token_counts),
            "truncation_count": sum(bool(item["truncated"]) for item in embedded_items),
        },
        "query_latency_ms": {
            "p50": statistics.median(query_latencies),
            "p95": percentile(query_latencies, 0.95),
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
