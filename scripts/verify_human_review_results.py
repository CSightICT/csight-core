"""Verify frozen Human Review Dev/Test artifacts without rerunning sealed Test."""

from __future__ import annotations

import json
from pathlib import Path

from app.platform.human_review import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evaluation/human_review_workflow_v1"


def main() -> int:
    records = [
        json.loads(line)
        for line in (BASE / "gold.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    profile = json.loads((BASE / "frozen_profile.json").read_text(encoding="utf-8"))
    assert canonical_hash(records) == manifest["content_hash"] == profile["dataset_hash"]
    for split, expected_count in (("dev", 60), ("test", 30)):
        metrics = json.loads(
            (BASE / "results" / f"{split}_metrics.json").read_text(encoding="utf-8")
        )
        assert metrics["record_count"] == expected_count
        assert metrics["dataset_hash"] == manifest["content_hash"]
        for key, value in metrics.items():
            if (
                key.endswith("_accuracy")
                or key.endswith("_rate")
                or key == "decision_basis_validity"
            ):
                assert value == 1.0, (split, key, value)
            if key.endswith("_count") and key != "record_count":
                assert value == 0, (split, key, value)
    print(
        json.dumps(
            {"status": "PASS", "dataset_hash": manifest["content_hash"], "dev": 60, "test": 30},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
