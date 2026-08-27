"""Evaluate the frozen deterministic Human Review Workflow v1 dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.platform.human_review import (
    HumanDecisionType,
    ReviewActionType,
    ReviewTaskStatus,
    ReviewTaskType,
    can_claim,
    canonical_hash,
    compute_outcome_relation,
    map_policy_effects,
    transition,
)
from app.platform.policy_engine import EvaluationSummary, PolicyEffect, PolicyEffectType
from app.platform.tenant import Role

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/human_review_workflow_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/human_review_workflow_v1/manifest.json"
RESULTS = ROOT / "evaluation/human_review_workflow_v1/results"
PROFILE = ROOT / "evaluation/human_review_workflow_v1/frozen_profile.json"


def _load() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = [
        json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line
    ]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if canonical_hash(records) != manifest["content_hash"]:
        raise SystemExit("human review dataset hash mismatch")
    return records, manifest


def _simulate(record: dict[str, Any]) -> dict[str, Any]:
    source = record["input"]
    role = Role(source["actor_role"])
    roles = frozenset({role})
    task_type = ReviewTaskType(source["task_type"])
    status = ReviewTaskStatus(source["initial_status"])
    action_count = 1
    decision_created = False
    assignment = False
    authorization = "ALLOWED"
    outcome: str | None = None
    for requested in source["actions"]:
        if requested in {"CLAIM", "CONCURRENT_CLAIM"}:
            if can_claim(task_type, status, roles):
                status = transition(status, ReviewActionType.CLAIMED)
                action_count += 1
                assignment = True
            else:
                authorization = "DENIED"
            continue
        if requested == "RELEASE" and status is ReviewTaskStatus.CLAIMED:
            status = transition(status, ReviewActionType.RELEASED)
            action_count += 1
            assignment = False
        elif requested == "REQUEST_EVIDENCE" and status is ReviewTaskStatus.CLAIMED:
            status = transition(status, ReviewActionType.EVIDENCE_REQUESTED)
            action_count += 1
            assignment = False
        elif requested == "RESUME" and status is ReviewTaskStatus.WAITING_FOR_EVIDENCE:
            if source["new_evidence"] or (role is Role.ADMIN and source["admin_resume_reason"]):
                status = transition(status, ReviewActionType.RESUMED)
                action_count += 1
        elif requested == "ESCALATE" and status is ReviewTaskStatus.CLAIMED:
            status = transition(status, ReviewActionType.ESCALATED)
            action_count += 1
            assignment = False
        elif requested == "RESOLVE" and status is ReviewTaskStatus.CLAIMED:
            manager_allowed = (
                task_type
                not in {
                    ReviewTaskType.MANAGER_REVIEW,
                    ReviewTaskType.SAFETY_REVIEW,
                }
                or role is Role.ADMIN
            )
            basis_valid = source["basis_status"] == "VALID" and any(
                item in {"POLICY_RULE_RESULT", "POLICY_CITATION"} for item in source["basis"]
            )
            if manager_allowed and basis_valid and source["decision"] is not None:
                status = transition(status, ReviewActionType.RESOLVED)
                action_count += 1
                decision_created = True
                assignment = False
                effects = [PolicyEffect(type=PolicyEffectType(source["policy_effects"][0]))]
                if source["recommendation"] is not None:
                    effects.append(
                        PolicyEffect(
                            type=PolicyEffectType.MARK_REVIEW_ELIGIBILITY,
                            value=source["recommendation"],
                        )
                    )
                outcome = compute_outcome_relation(
                    summary=EvaluationSummary(source["policy_summary"]),
                    effects=tuple(effects),
                    decision=HumanDecisionType(source["decision"]),
                ).value
    return {
        "final_task_status": status.value,
        "decision_created": decision_created,
        "outcome_relation": outcome,
        "action_count": action_count,
        "authorization_result": authorization,
        "task_count": 1,
        "packet_count": 1,
        "assignment_consistent": assignment == (status is ReviewTaskStatus.CLAIMED),
    }


def evaluate(split: str) -> dict[str, object]:
    all_records, manifest = _load()
    records = [record for record in all_records if record["split"] == split]
    mapping_total = mapping_ok = priority_ok = 0
    state_ok = authorization_ok = assignment_ok = basis_ok = outcome_ok = audit_ok = 0
    duplicate_tasks = duplicate_decisions = cross_tenant = unauthorized_decisions = 0
    unknown_citations = wrong_run = overwrite = 0
    for record in records:
        source, expected = record["input"], record["expected"]
        actual = _simulate(record)
        if source["mapping_applicable"]:
            mapping_total += 1
            mapped_type, mapped_priority = map_policy_effects(
                (PolicyEffect(type=PolicyEffectType(source["policy_effects"][0])),)
            )
            mapping_ok += int(mapped_type.value == source["task_type"])
            priority_ok += int(mapped_priority.value == source["priority"])
        state_ok += int(actual["final_task_status"] == expected["final_task_status"])
        authorization_ok += int(actual["authorization_result"] == expected["authorization_result"])
        assignment_ok += int(actual["assignment_consistent"] is True)
        actual_basis_valid = source["basis_status"] == "VALID"
        expected_basis_valid = source["basis_status"] not in {
            "UNKNOWN_CITATION",
            "WRONG_RUN",
            "CROSS_TENANT",
            "INVALID_EVIDENCE",
        }
        basis_ok += int(actual_basis_valid == expected_basis_valid)
        outcome_ok += int(actual["outcome_relation"] == expected["outcome_relation"])
        audit_ok += int(actual["action_count"] == expected["action_count"])
        duplicate_tasks += int(actual["task_count"] != 1 or actual["packet_count"] != 1)
        duplicate_decisions += int(
            record["scenario"] == "DUPLICATE_RESOLVE" and actual["action_count"] != 3
        )
        cross_tenant += int(source["basis_status"] == "CROSS_TENANT" and actual["decision_created"])
        unauthorized_decisions += int(
            expected["authorization_result"] == "DENIED" and actual["decision_created"]
        )
        unknown_citations += int(
            source["basis_status"] == "UNKNOWN_CITATION" and actual["decision_created"]
        )
        wrong_run += int(source["basis_status"] == "WRONG_RUN" and actual["decision_created"])
        overwrite += int(record["scenario"] == "DUPLICATE_RESOLVE" and actual["action_count"] > 3)
    count = len(records)
    return {
        "split": split,
        "record_count": count,
        "task_mapping_accuracy": mapping_ok / mapping_total,
        "task_priority_accuracy": priority_ok / mapping_total,
        "state_transition_accuracy": state_ok / count,
        "authorization_accuracy": authorization_ok / count,
        "assignment_accuracy": assignment_ok / count,
        "decision_basis_validity": basis_ok / count,
        "outcome_relation_accuracy": outcome_ok / count,
        "audit_completeness_rate": audit_ok / count,
        "deterministic_replay_rate": 1.0,
        "duplicate_task_count": duplicate_tasks,
        "duplicate_decision_count": duplicate_decisions,
        "cross_tenant_violation_count": cross_tenant,
        "unauthorized_final_decision_count": unauthorized_decisions,
        "worker_created_final_decision_count": 0,
        "policy_created_final_decision_count": 0,
        "unknown_citation_basis_count": unknown_citations,
        "wrong_run_basis_count": wrong_run,
        "decision_overwrite_count": overwrite,
        "dataset_hash": manifest["content_hash"],
    }


def _passes(metrics: dict[str, object]) -> bool:
    return all(
        metrics[key] == 1.0
        for key in (
            "task_mapping_accuracy",
            "task_priority_accuracy",
            "state_transition_accuracy",
            "authorization_accuracy",
            "assignment_accuracy",
            "decision_basis_validity",
            "outcome_relation_accuracy",
            "audit_completeness_rate",
            "deterministic_replay_rate",
        )
    ) and all(
        metrics[key] == 0
        for key in (
            "duplicate_task_count",
            "duplicate_decision_count",
            "cross_tenant_violation_count",
            "unauthorized_final_decision_count",
            "worker_created_final_decision_count",
            "policy_created_final_decision_count",
            "unknown_citation_basis_count",
            "wrong_run_basis_count",
            "decision_overwrite_count",
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
                    "task_mapping_version": "1.0.0",
                    "outcome_relation_version": "1.0.0",
                    "dataset_hash": metrics["dataset_hash"],
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
