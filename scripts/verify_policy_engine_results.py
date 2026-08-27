"""Verify frozen Policy Engine Dev/Test artifacts without rerunning sealed Test."""

import json
from pathlib import Path

from app.platform.policy_engine import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evaluation/policy_engine_v1"


def main() -> int:
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    profile = json.loads((BASE / "frozen_profile.json").read_text(encoding="utf-8"))
    dev = json.loads((BASE / "results/dev_metrics.json").read_text(encoding="utf-8"))
    test = json.loads((BASE / "results/test_metrics.json").read_text(encoding="utf-8"))
    ok = (
        profile["dataset_hash"]
        == manifest["content_hash"]
        == dev["dataset_hash"]
        == test["dataset_hash"]
        and profile["rule_artifact_hash"]
        == manifest["rule_set_artifact_hash"]
        == dev["rule_artifact_hash"]
        == test["rule_artifact_hash"]
        and profile["dev_metrics_hash"] == canonical_hash(dev)
        and all(
            metrics[key] == 1.0
            for metrics in (dev, test)
            for key in (
                "rule_set_selection_accuracy",
                "rule_match_exact_accuracy",
                "condition_status_accuracy",
                "effect_f1",
                "summary_status_accuracy",
                "source_clause_validity",
                "rule_version_accuracy",
                "deterministic_replay_rate",
            )
        )
        and all(
            metrics[key] == 0
            for metrics in (dev, test)
            for key in (
                "cross_tenant_rule_selection",
                "future_or_retired_rule_set",
                "forbidden_final_decision_count",
            )
        )
    )
    print(
        json.dumps(
            {"status": "PASS" if ok else "FAIL", "dev": dev, "test": test}, indent=2, sort_keys=True
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
