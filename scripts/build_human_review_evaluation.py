"""Build the sealed 60/30 synthetic Human Review Workflow v1 gold set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.platform.human_review import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation/human_review_workflow_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/human_review_workflow_v1/manifest.json"


def _record(
    scenario: str,
    *,
    effect: str,
    task_type: str,
    priority: str,
    role: str,
    actions: list[str],
    final_status: str,
    action_count: int,
    allowed: bool = True,
    decision: str | None = None,
    basis: list[str] | None = None,
    basis_status: str = "VALID",
    outcome: str | None = None,
    duplicate_events: int = 1,
    new_evidence: bool = False,
    admin_resume_reason: bool = False,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "input": {
            "policy_effects": [effect],
            "task_type": task_type,
            "priority": priority,
            "initial_status": "PENDING",
            "actor_role": role,
            "actor_is_assignee": True,
            "actions": actions,
            "decision": decision,
            "basis": basis or [],
            "basis_status": basis_status,
            "policy_summary": (
                "BLOCKED_INPUT_INCOMPLETE"
                if outcome == "INDETERMINATE_POLICY"
                else "REQUIRES_HUMAN_REVIEW"
            ),
            "recommendation": (
                "EXCHANGE_REVIEW"
                if outcome
                in {
                    "CONSISTENT_WITH_RECOMMENDATION",
                    "DIFFERS_FROM_RECOMMENDATION",
                }
                else None
            ),
            "mapping_applicable": scenario != "SAFETY_ADMIN_RESOLVE",
            "duplicate_event_count": duplicate_events,
            "new_evidence": new_evidence,
            "admin_resume_reason": admin_resume_reason,
        },
        "expected": {
            "final_task_status": final_status,
            "decision_created": decision is not None and basis_status == "VALID" and allowed,
            "outcome_relation": outcome,
            "action_count": action_count,
            "authorization_result": "ALLOWED" if allowed else "DENIED",
            "task_count": 1,
            "packet_count": 1,
        },
        "forbidden": [
            "AUTOMATED_DECISION",
            "CROSS_TENANT_REFERENCE",
            "DECISION_OVERWRITE",
        ],
    }


def _templates() -> list[dict[str, Any]]:
    standard: dict[str, Any] = dict(
        effect="REQUIRE_HUMAN_REVIEW",
        task_type="STANDARD_REVIEW",
        priority="NORMAL",
    )
    return [
        _record(
            "STANDARD_RESOLVE",
            **standard,
            role="REVIEWER",
            actions=["CLAIM", "RESOLVE"],
            decision="APPROVE_EXCHANGE",
            basis=["POLICY_RULE_RESULT"],
            final_status="RESOLVED",
            action_count=3,
            outcome="CONSISTENT_WITH_RECOMMENDATION",
        ),
        _record(
            "STANDARD_RELEASE",
            **standard,
            role="REVIEWER",
            actions=["CLAIM", "RELEASE"],
            final_status="PENDING",
            action_count=3,
        ),
        _record(
            "EVIDENCE_REQUEST",
            effect="REQUIRE_ADDITIONAL_EVIDENCE",
            task_type="EVIDENCE_REVIEW",
            priority="NORMAL",
            role="REVIEWER",
            actions=["CLAIM", "REQUEST_EVIDENCE"],
            final_status="WAITING_FOR_EVIDENCE",
            action_count=3,
        ),
        _record(
            "EVIDENCE_RESUME",
            effect="REQUIRE_ADDITIONAL_EVIDENCE",
            task_type="EVIDENCE_REVIEW",
            priority="NORMAL",
            role="REVIEWER",
            actions=["CLAIM", "REQUEST_EVIDENCE", "RESUME"],
            final_status="PENDING",
            action_count=4,
            new_evidence=True,
        ),
        _record(
            "MANAGER_REVIEWER_DENIED",
            effect="REQUIRE_MANAGER_REVIEW",
            task_type="MANAGER_REVIEW",
            priority="HIGH",
            role="REVIEWER",
            actions=["CLAIM"],
            final_status="PENDING",
            action_count=1,
            allowed=False,
        ),
        _record(
            "MANAGER_ADMIN_RESOLVE",
            effect="REQUIRE_MANAGER_REVIEW",
            task_type="MANAGER_REVIEW",
            priority="HIGH",
            role="ADMIN",
            actions=["CLAIM", "RESOLVE"],
            decision="APPROVE_REFUND",
            basis=["POLICY_CITATION"],
            final_status="RESOLVED",
            action_count=3,
            outcome="DIFFERS_FROM_RECOMMENDATION",
        ),
        _record(
            "POLICY_EXCEPTION_ESCALATE",
            effect="FLAG_POLICY_EXCEPTION",
            task_type="POLICY_EXCEPTION_REVIEW",
            priority="HIGH",
            role="REVIEWER",
            actions=["CLAIM", "ESCALATE"],
            final_status="ESCALATED",
            action_count=3,
        ),
        _record(
            "SAFETY_ADMIN_RESOLVE",
            effect="PROHIBIT_AUTOMATION",
            task_type="SAFETY_REVIEW",
            priority="CRITICAL",
            role="ADMIN",
            actions=["CLAIM", "RESOLVE"],
            decision="NO_ACTION",
            basis=["POLICY_RULE_RESULT"],
            final_status="RESOLVED",
            action_count=3,
            outcome="NO_COMPARABLE_RECOMMENDATION",
        ),
        _record(
            "VIEWER_READ_ONLY",
            **standard,
            role="QUALITY_VIEWER",
            actions=["CLAIM"],
            final_status="PENDING",
            action_count=1,
            allowed=False,
        ),
        _record(
            "CONCURRENT_CLAIM",
            **standard,
            role="REVIEWER",
            actions=["CONCURRENT_CLAIM"],
            final_status="CLAIMED",
            action_count=2,
        ),
        _record(
            "DUPLICATE_EVENT",
            **standard,
            role="REVIEWER",
            actions=[],
            final_status="PENDING",
            action_count=1,
            duplicate_events=2,
        ),
        _record(
            "DUPLICATE_RESOLVE",
            **standard,
            role="REVIEWER",
            actions=["CLAIM", "RESOLVE", "RESOLVE"],
            decision="APPROVE_EXCHANGE",
            basis=["POLICY_RULE_RESULT"],
            final_status="RESOLVED",
            action_count=3,
            outcome="CONSISTENT_WITH_RECOMMENDATION",
        ),
        _record(
            "UNKNOWN_CITATION",
            **standard,
            role="REVIEWER",
            actions=["CLAIM", "RESOLVE"],
            decision="REJECT_REQUEST",
            basis=["POLICY_CITATION"],
            basis_status="UNKNOWN_CITATION",
            final_status="CLAIMED",
            action_count=2,
        ),
        _record(
            "WRONG_RUN_RULE",
            **standard,
            role="REVIEWER",
            actions=["CLAIM", "RESOLVE"],
            decision="REJECT_REQUEST",
            basis=["POLICY_RULE_RESULT"],
            basis_status="WRONG_RUN",
            final_status="CLAIMED",
            action_count=2,
        ),
        _record(
            "CROSS_TENANT_BASIS",
            **standard,
            role="ADMIN",
            actions=["CLAIM", "RESOLVE"],
            decision="REJECT_REQUEST",
            basis=["POLICY_CITATION"],
            basis_status="CROSS_TENANT",
            final_status="CLAIMED",
            action_count=2,
        ),
    ]


def build() -> list[dict[str, Any]]:
    templates = _templates()
    records: list[dict[str, Any]] = []
    for index in range(90):
        template = templates[index % len(templates)]
        record = json.loads(json.dumps(template))
        record["record_id"] = f"HR-{index + 1:04d}"
        record["split"] = "dev" if index < 60 else "test"
        records.append(record)
    return records


def main() -> int:
    records = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "dataset": "human_review_workflow_v1",
        "schema_version": "1.0.0",
        "builder_version": "1.0.0",
        "dev_count": 60,
        "test_count": 30,
        "total_count": 90,
        "test_sealed": True,
        "content_hash": canonical_hash(records),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
