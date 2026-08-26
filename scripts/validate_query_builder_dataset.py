"""Fail-closed validation for the sealed query-builder holdout."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data_path = ROOT / "evaluation/policy_query_builder_v1/gold.jsonl"
    manifest = json.loads((data_path.parent / "manifest.json").read_text())
    payload = data_path.read_bytes()
    records = [json.loads(line) for line in payload.splitlines() if line]
    clauses = {
        item["clause_id"]: item
        for item in (
            json.loads(line)
            for line in (ROOT / "data/policy_corpus/clauses/policy_clauses_v1.jsonl")
            .read_text()
            .splitlines()
            if line
        )
    }
    legacy = {
        json.loads(line).get("query_text", "")
        for line in (ROOT / "evaluation/policy_retrieval_v1/gold.jsonl").read_text().splitlines()
        if line
    }
    counts = Counter(record["split"] for record in records)
    assert counts == {"dev": 80, "test": 40}
    assert len({record["record_id"] for record in records}) == 120
    assert hashlib.sha256(payload).hexdigest() == manifest["dataset_hash"]
    assert manifest["test_sealed"] is True
    assert not ({record["customer_message"] for record in records} & legacy)
    for record in records:
        for clause_id in record["relevant_clause_ids"] + record["hard_negative_clause_ids"]:
            clause = clauses[clause_id]
            assert clause["tenant_id"] == record["tenant_id"]
            assert clause["document_status"] == "ACTIVE"
            assert clause["effective_from"] <= record["as_of_date"]
            assert clause["effective_to"] is None or record["as_of_date"] <= clause["effective_to"]
        for clause_id in record["forbidden_clause_ids"]:
            assert clauses[clause_id]["tenant_id"] != record["tenant_id"]
    print(
        "QUERY_BUILDER_DATASET_VALID dev=80 test=40 broken_gold=0 "
        f"cross_tenant=0 stable_hash={manifest['dataset_hash']} test_sealed=true"
    )


if __name__ == "__main__":
    main()
