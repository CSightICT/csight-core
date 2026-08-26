"""Fail-closed validation for all Sprint 4A synthetic evaluation datasets."""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "evaluation"


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validate() -> dict[str, int]:
    clauses = _load(ROOT / "data/policy_corpus/clauses/policy_clauses_v1.jsonl")
    clause_map = {item["clause_id"]: item for item in clauses}
    extraction = _load(EVALUATION / "llm_extraction_v2/gold.jsonl")
    retrieval = _load(EVALUATION / "policy_retrieval_v1/gold.jsonl")
    grounding = _load(EVALUATION / "rag_grounding_v1/gold.jsonl")
    injection = _load(EVALUATION / "prompt_injection_v1/gold.jsonl")
    demos = _load(EVALUATION / "reference_demo_v1/demo_pack.jsonl")
    expected = {
        "extraction": (extraction, 160, {"dev": 120, "test": 40}),
        "retrieval": (retrieval, 120, {"dev": 80, "test": 40}),
        "grounding": (grounding, 50, {"dev": 40, "test": 10}),
        "injection": (injection, 30, {"dev": 20, "test": 10}),
    }
    for name, (records, count, splits) in expected.items():
        if len(records) != count:
            raise ValueError(f"{name} count mismatch")
        actual_splits = {split: sum(item["split"] == split for item in records) for split in splits}
        if actual_splits != splits:
            raise ValueError(f"{name} split mismatch")
    if len(demos) != 10:
        raise ValueError("demo count mismatch")
    for record in extraction:
        message = record["customer_message"]
        if any(quote not in message for quote in record["allowed_source_quotes"]):
            raise ValueError("extraction source quote is not contiguous")
    cross_tenant = 0
    missing_gold = 0
    for record in retrieval:
        tenant = record["tenant_id"]
        for clause_id in record["relevant_clause_ids"] + record["hard_negative_clause_ids"]:
            clause = clause_map.get(clause_id)
            if clause is None:
                missing_gold += 1
            elif clause["tenant_id"] != tenant:
                cross_tenant += 1
        for clause_id in record["forbidden_clause_ids"]:
            clause = clause_map.get(clause_id)
            if clause is None:
                missing_gold += 1
            elif clause["tenant_id"] == tenant:
                cross_tenant += 1
    for record in grounding:
        for clause_id in record["provided_clause_ids"] + record["required_citation_ids"]:
            clause = clause_map.get(clause_id)
            if clause is None:
                missing_gold += 1
            elif clause["tenant_id"] != record["tenant_id"]:
                cross_tenant += 1
    if missing_gold or cross_tenant:
        raise ValueError(
            f"gold reference validation failed: missing={missing_gold} cross_tenant={cross_tenant}"
        )
    if len({item["category"] for item in injection}) < 8:
        raise ValueError("prompt injection category coverage is incomplete")
    return {
        "gold_clause_missing_count": missing_gold,
        "cross_tenant_gold_violation_count": cross_tenant,
        "extraction_count": len(extraction),
        "retrieval_count": len(retrieval),
        "grounding_count": len(grounding),
        "injection_count": len(injection),
        "demo_count": len(demos),
    }


def main() -> None:
    result = validate()
    print("EVALUATION_DATA_VALID " + " ".join(f"{key}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
