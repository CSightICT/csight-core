"""Private, non-overwriting Dev reports with explicit clause-ranking metrics."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.platform.retrieval_evaluation import (
    RetrievalEvaluationObservation,
    compute_retrieval_metrics,
)


def ranking_metrics_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    report = compute_retrieval_metrics(
        tuple(
            RetrievalEvaluationObservation(
                record_id=row["record_id"],
                relevant_clause_ids=tuple(row["relevant"]),
                hit_clause_ids=tuple(row["hits"]),
                success=row.get("success", True),
            )
            for row in rows
        )
    )
    values: dict[str, Any] = {
        "metrics_schema_version": report.schema_version,
        "recall_semantics": "MACRO_FRACTION_OF_RELEVANT_CLAUSES",
        "release_eligible": False,
        "record_count": report.record_count,
        "success_count": report.success_count,
        "failed_count": report.failed_count,
        "mrr_at_10": report.mrr_at_10,
        "ndcg_at_10": report.ndcg_at_10,
        "zero_result_rate": report.zero_result_rate,
    }
    for item in report.cutoffs:
        values[f"recall_at_{item.cutoff}"] = item.clause_recall
        values[f"clause_recall_at_{item.cutoff}"] = item.clause_recall
        values[f"hit_rate_at_{item.cutoff}"] = item.hit_rate
        values[f"exact_gold_coverage_at_{item.cutoff}"] = item.exact_gold_coverage
    values["candidate_recall_at_20"] = values["clause_recall_at_20"]
    return values


def unmeasured_metrics(*names: str) -> dict[str, Any]:
    """Absence of a dedicated observation is not zero violations or perfect success."""
    return {**{name: None for name in names}, "unmeasured_checks": dict.fromkeys(names, "NOT_RUN")}


def reserve_new_output(directory: Path | None) -> Path:
    """Reserve before provider construction. Never reuse even an empty prior run."""
    if directory is None:
        raise ValueError("NEW_OUTPUT_DIRECTORY_REQUIRED")
    directory.mkdir(mode=0o700)
    return directory


def write_json_new(path: Path, value: object) -> str:
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()


def private_observation_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """No query, quote, model plan, error message, URL or identifier is copied to disk."""
    result: list[dict[str, Any]] = []
    for row in rows:
        summary: dict[str, Any] = {
            "record_id_hash": hashlib.sha256(str(row["record_id"]).encode()).hexdigest(),
            "success": row.get("success", True) is True,
            "observation_hash": hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
        }
        if "relevant" in row and "hits" in row:
            for source, target in (("relevant", "relevant_hashes"), ("hits", "hit_hashes")):
                summary[target] = [
                    hashlib.sha256(str(identifier).encode()).hexdigest()
                    for identifier in row[source]
                ]
        result.append(summary)
    return result
