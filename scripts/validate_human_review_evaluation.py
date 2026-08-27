"""Validate counts, sealing, hashes, schema, and scenario coverage for Human Review v1."""

from __future__ import annotations

import json
from pathlib import Path

from app.platform.human_review import (
    ReviewPriority,
    ReviewTaskStatus,
    ReviewTaskType,
    canonical_hash,
)
from app.platform.tenant import Role

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/human_review_workflow_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/human_review_workflow_v1/manifest.json"


def main() -> int:
    records = [
        json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line
    ]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(records) == 90
    assert sum(item["split"] == "dev" for item in records) == 60
    assert sum(item["split"] == "test" for item in records) == 30
    assert manifest["test_sealed"] is True
    assert manifest["content_hash"] == canonical_hash(records)
    assert len({item["record_id"] for item in records}) == 90
    types = {item["input"]["task_type"] for item in records}
    roles = {item["input"]["actor_role"] for item in records}
    scenarios = {item["scenario"] for item in records}
    assert types == {item.value for item in ReviewTaskType}
    assert roles == {item.value for item in Role}
    assert all(
        item["input"]["priority"] in {value.value for value in ReviewPriority} for item in records
    )
    assert all(
        item["expected"]["final_task_status"] in {value.value for value in ReviewTaskStatus}
        for item in records
    )
    required = {
        "STANDARD_RESOLVE",
        "STANDARD_RELEASE",
        "EVIDENCE_REQUEST",
        "EVIDENCE_RESUME",
        "MANAGER_REVIEWER_DENIED",
        "MANAGER_ADMIN_RESOLVE",
        "POLICY_EXCEPTION_ESCALATE",
        "SAFETY_ADMIN_RESOLVE",
        "VIEWER_READ_ONLY",
        "CONCURRENT_CLAIM",
        "DUPLICATE_EVENT",
        "DUPLICATE_RESOLVE",
        "UNKNOWN_CITATION",
        "WRONG_RUN_RULE",
        "CROSS_TENANT_BASIS",
    }
    assert required <= scenarios
    print(
        json.dumps(
            {
                "records": 90,
                "dev": 60,
                "test": 30,
                "coverage": len(scenarios),
                "content_hash": manifest["content_hash"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
