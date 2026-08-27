"""Evaluate the frozen deterministic Policy Engine v1 dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.platform.policy_engine import (
    PolicyEvaluationInput,
    PolicyRuleSet,
    SourceQualification,
    canonical_hash,
    evaluate_rule_set,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/policy_engine_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/policy_engine_v1/manifest.json"
RULES = ROOT / "data/policy_rules/normalized/policy_rule_sets_v1.jsonl"
RESULTS = ROOT / "evaluation/policy_engine_v1/results"
PROFILE = ROOT / "evaluation/policy_engine_v1/frozen_profile.json"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _actual_rule_results(result: object) -> list[dict[str, Any]]:
    from app.platform.policy_engine import PolicyEvaluation

    if not isinstance(result, PolicyEvaluation):
        raise TypeError("evaluation result is invalid")
    return [
        {
            "rule_id": item.rule_id,
            "rule_version": item.rule_version,
            "status": item.status.value,
            "condition_statuses": [condition.status.value for condition in item.condition_results],
            "effects": sorted(effect.type.value for effect in item.effects),
            "source_clause_ids": list(item.source_clause_ids),
        }
        for item in result.rule_results
    ]


def evaluate(split: str) -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    all_records = _load_jsonl(DATASET)
    if canonical_hash(all_records) != manifest["content_hash"]:
        raise SystemExit("dataset hash mismatch")
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in RULES.read_text(encoding="utf-8").splitlines()
        if line
    )
    by_tenant = {item.tenant_slug: item for item in rule_sets}
    records = [item for item in all_records if item["split"] == split]
    selection_ok = rule_ok = condition_ok = summary_ok = source_ok = version_ok = 0
    effect_tp = effect_fp = effect_fn = 0
    forbidden = replay_failures = tenant_failures = effective_failures = 0
    for record in records:
        rule_set = by_tenant.get(record["tenant_id"])
        expected = record["expected"]
        selected = (
            rule_set is not None
            and rule_set.effective_from.isoformat() <= record["as_of_date"]
            and (
                rule_set.effective_to is None
                or rule_set.effective_to.isoformat() >= record["as_of_date"]
            )
        )
        expected_selected = expected["selection_status"] == "SELECTED"
        selection_ok += int(selected == expected_selected)
        if not selected:
            effective_failures += int(expected_selected)
            continue
        assert rule_set is not None
        tenant_failures += int(rule_set.tenant_slug != record["tenant_id"])
        policy_input = PolicyEvaluationInput(
            values=record["input"]["values"],
            llm_qualification=SourceQualification(record["input"]["llm_qualification"]),
            vision_qualification=SourceQualification(record["input"]["vision_qualification"]),
            alignment_qualification=SourceQualification(record["input"]["alignment_qualification"]),
        )
        first = evaluate_rule_set(rule_set, policy_input)
        second = evaluate_rule_set(rule_set, policy_input)
        replay_failures += int(first.model_dump(mode="json") != second.model_dump(mode="json"))
        actual_rules = _actual_rule_results(first)
        expected_rules = expected["rule_results"]
        rule_ok += int(actual_rules == expected_rules)
        condition_ok += int(
            [r["condition_statuses"] for r in actual_rules]
            == [r["condition_statuses"] for r in expected_rules]
        )
        summary_ok += int(first.summary_status.value == expected["summary_status"])
        version_ok += int(
            first.rule_set_version == expected["rule_set_version"]
            and first.rule_set_hash == expected["rule_set_hash"]
        )
        source_ok += int(all(r["source_clause_ids"] for r in actual_rules))
        expected_effects = {effect for row in expected_rules for effect in row["effects"]}
        actual_effects = {effect for row in actual_rules for effect in row["effects"]}
        effect_tp += len(expected_effects & actual_effects)
        effect_fp += len(actual_effects - expected_effects)
        effect_fn += len(expected_effects - actual_effects)
        serialized = json.dumps(first.model_dump(mode="json"), sort_keys=True)
        forbidden += sum(token in serialized for token in record["forbidden_outputs"])
    selected_count = sum(record["expected"]["selection_status"] == "SELECTED" for record in records)
    precision = effect_tp / (effect_tp + effect_fp) if effect_tp + effect_fp else 1.0
    recall = effect_tp / (effect_tp + effect_fn) if effect_tp + effect_fn else 1.0
    effect_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    metrics: dict[str, object] = {
        "split": split,
        "record_count": len(records),
        "rule_set_selection_accuracy": selection_ok / len(records),
        "rule_match_exact_accuracy": rule_ok / selected_count,
        "condition_status_accuracy": condition_ok / selected_count,
        "effect_precision": precision,
        "effect_recall": recall,
        "effect_f1": effect_f1,
        "summary_status_accuracy": summary_ok / selected_count,
        "source_clause_validity": source_ok / selected_count,
        "rule_version_accuracy": version_ok / selected_count,
        "cross_tenant_rule_selection": tenant_failures,
        "future_or_retired_rule_set": effective_failures,
        "forbidden_final_decision_count": forbidden,
        "deterministic_replay_rate": 1 - replay_failures / selected_count,
        "dataset_hash": manifest["content_hash"],
        "rule_artifact_hash": manifest["rule_set_artifact_hash"],
    }
    return metrics


def _passes(metrics: dict[str, object]) -> bool:
    accuracy_keys = (
        "rule_set_selection_accuracy",
        "rule_match_exact_accuracy",
        "condition_status_accuracy",
        "effect_f1",
        "summary_status_accuracy",
        "source_clause_validity",
        "rule_version_accuracy",
        "deterministic_replay_rate",
    )
    return all(metrics[key] == 1.0 for key in accuracy_keys) and all(
        metrics[key] == 0
        for key in (
            "cross_tenant_rule_selection",
            "future_or_retired_rule_set",
            "forbidden_final_decision_count",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--freeze-profile", action="store_true")
    parser.add_argument("--sealed-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.split == "test" and not arguments.sealed_test:
        raise SystemExit("sealed Test requires --sealed-test")
    output = RESULTS / f"{arguments.split}_metrics.json"
    if arguments.split == "test" and output.exists():
        raise SystemExit("sealed Test artifact already exists; rerun refused")
    metrics = evaluate(arguments.split)
    RESULTS.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if arguments.freeze_profile:
        if arguments.split != "dev":
            raise SystemExit("only Dev can freeze the evaluation profile")
        PROFILE.write_text(
            json.dumps(
                {
                    "profile_version": "1.0.0",
                    "aggregation_version": "1.0.0",
                    "dataset_hash": metrics["dataset_hash"],
                    "rule_artifact_hash": metrics["rule_artifact_hash"],
                    "dev_metrics_hash": canonical_hash(metrics),
                    "frozen_after_split": "dev",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0 if _passes(metrics) else 1


if __name__ == "__main__":
    raise SystemExit(main())
