"""Acceptance tests for the synthetic hard-plastic scenario PoC gate."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from scripts.verify_scenario_poc import (
    SAFE_CLAIMS_BOUNDARY,
    OfflinePackStatus,
    RuntimeVisionStatus,
    ScenarioPocVerdict,
    assess_scenario_poc,
    build_acceptance_report,
    validate_acceptance_report,
)

pytestmark = pytest.mark.unit

BOUNDARIES = (
    "COMPLETE_VISIBLE_BREAKAGE_DRY_RUN_VALIDATED",
    "REFUND_INPUT_MISSING_NO_ATTEMPT",
    "FUNCTIONAL_FAILURE_STILL_UNCONFIRMED_REQUEST_EVIDENCE",
    "SAFETY_REVIEWER_BLOCKED_ADMIN_RESOLVE",
    "VISION_TIMEOUT_PARTIAL_SUCCESS_NO_ACTION",
)
ARTIFACTS = (
    "cases.jsonl",
    "policy.json",
    "gold.jsonl",
    "demo_scenarios.json",
    "model_manifest.json",
)


def _dump_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dump_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(
        payload,
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reseal_manifest(path: Path) -> None:
    manifest = json.loads((path / "manifest.json").read_text())
    artifact_hashes = {filename: _sha256(path / filename) for filename in ARTIFACTS}
    manifest["artifact_hashes"] = artifact_hashes
    manifest["pack_hash"] = _canonical_hash(dict(sorted(artifact_hashes.items())))
    _dump_json(path / "manifest.json", manifest)


def _make_pack(path: Path, *, runtime_available: bool = False) -> Path:
    path.mkdir(parents=True)
    cases: list[dict[str, object]] = []
    gold: list[dict[str, object]] = []
    for index in range(30):
        record_id = f"HDP-{index + 1:04d}"
        cases.append(
            {
                "record_id": record_id,
                "split": "demo" if index < 5 else "evaluation",
                "scenario_tags": ["plastic_hard", "synthetic"],
                "case_input": {"customer_message": f"합성 문의 {index + 1}"},
            }
        )
        gold.append(
            {
                "record_id": record_id,
                "expected": {
                    "issue_types": ["BREAKAGE"],
                    "issue_evidence_basis": "CUSTOMER_TEXT_AND_IMAGE",
                    "vision": {
                        "score_band": "HIGH_CANDIDATE",
                        "business_interpretation": "HIGH_CONFIDENCE_DEFECT_CANDIDATE",
                        "type_or_location_claim_allowed": False,
                    },
                    "policy_clause_ids": ["SYN-HDP-POLICY-001:1.0.0:C1"],
                    "policy_effects": ["REQUIRE_HUMAN_REVIEW"],
                    "review": {
                        "task_type": "STANDARD_REVIEW",
                        "required_role": "REVIEWER",
                        "reviewer_claim_allowed": True,
                        "human_decision": "REPAIR",
                    },
                    "resolution": {
                        "status": "ACTION_DRY_RUN_VALIDATED",
                        "intent_count": 1,
                        "attempt_count": 1,
                        "result_count": 1,
                        "side_effects_performed": False,
                    },
                },
                "forbidden_outcomes": [
                    "AUTOMATED_DECISION",
                    "LIVE_EXTERNAL_ACTION",
                    "VISION_CONFIRMED_DEFECT_TYPE",
                    "VISION_CONFIRMED_DEFECT_LOCATION",
                    "NORMAL_FROM_LOW_SCORE",
                    "PARAMETER_INFERENCE",
                ],
            }
        )
    demo_2 = cast(dict[str, object], gold[1]["expected"])
    demo_2["resolution"] = {
        "status": "ACTION_NEEDS_INPUT",
        "intent_count": 0,
        "attempt_count": 0,
        "result_count": 0,
        "side_effects_performed": False,
    }
    for index in (2, 4):
        expected = cast(dict[str, object], gold[index]["expected"])
        expected["vision"] = (
            {
                "score_band": "BELOW_THRESHOLD",
                "business_interpretation": "NOT_NORMAL",
                "type_or_location_claim_allowed": False,
            }
            if index == 2
            else {
                "score_band": "UNAVAILABLE",
                "business_interpretation": "VISION_TIMEOUT",
                "type_or_location_claim_allowed": False,
            }
        )
        expected["review"] = {
            "task_type": "EVIDENCE_REVIEW",
            "required_role": "REVIEWER",
            "reviewer_claim_allowed": True,
            "human_decision": None,
        }
        expected["resolution"] = {
            "status": "NOT_CREATED",
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
            "side_effects_performed": False,
        }
    demo_4 = cast(dict[str, object], gold[3]["expected"])
    demo_4["review"] = {
        "task_type": "SAFETY_REVIEW",
        "required_role": "ADMIN",
        "reviewer_claim_allowed": False,
        "human_decision": "APPROVE_EXCHANGE",
    }
    _dump_jsonl(path / "cases.jsonl", cases)
    _dump_jsonl(path / "gold.jsonl", gold)
    _dump_json(
        path / "policy.json",
        {
            "schema_version": "synthetic_policy_bundle/1.0.0",
            "source_type": "SYNTHETIC_REFERENCE",
            "document": {
                "version": "1.0.0",
                "effective_from": "2026-08-27",
                "effective_to": None,
                "status": "ACTIVE",
                "fictional": True,
                "legal_or_commercial_effect": False,
            },
            "clauses": [
                {
                    "clause_id": "SYN-HDP-POLICY-001:1.0.0:C1",
                    "version": "1.0.0",
                    "effective_from": "2026-08-27",
                    "text": "합성 데모 정책",
                }
            ],
            "global_guardrails": {
                "final_decision_owner": "AUTHENTICATED_HUMAN",
                "automatic_approval_allowed": False,
                "parameter_inference_allowed": False,
                "external_action_mode": "DRY_RUN",
                "live_external_action_allowed": False,
                "side_effects_performed": False,
                "actual_performance_or_roi_claim_allowed": False,
            },
        },
    )
    scenario_assertions: tuple[dict[str, object], ...] = (
        {
            "human_decision_required": True,
            "resolution_status": "ACTION_DRY_RUN_VALIDATED",
            "intent_count": 1,
            "attempt_count": 1,
            "result_count": 1,
            "side_effects_performed": False,
        },
        {
            "human_decision_required": True,
            "resolution_status": "ACTION_NEEDS_INPUT",
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
            "parameter_inference": False,
        },
        {
            "functional_failure_source": "TEXT_CLAIM",
            "still_image_confirms_function": False,
            "review_task_type": "EVIDENCE_REVIEW",
            "human_decision_count": 0,
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
        },
        {
            "required_role": "ADMIN",
            "reviewer_claim_allowed": False,
            "resolution_status": "ACTION_DRY_RUN_VALIDATED",
            "side_effects_performed": False,
            "live_external_action": False,
        },
        {
            "analysis_outcome": "PARTIAL_SUCCESS",
            "vision_status": "TIMEOUT",
            "human_review_required": True,
            "human_decision_count": 0,
            "intent_count": 0,
            "attempt_count": 0,
            "result_count": 0,
        },
    )
    scenarios = [
        {
            "scenario_id": f"DEMO-{index + 1}",
            "case_record_id": f"HDP-{index + 1:04d}",
            "title": boundary,
            "boundary": boundary,
            "expected_assertions": scenario_assertions[index],
        }
        for index, boundary in enumerate(BOUNDARIES)
    ]
    _dump_json(
        path / "demo_scenarios.json",
        {"schema_version": "1.0.0", "scenario_count": 5, "scenarios": scenarios},
    )
    _dump_json(
        path / "model_manifest.json",
        {
            "schema_version": "scenario_vision_model/1.0.0",
            "source_type": "SUPPLIED_OFFLINE_REPORT",
            "candidate": {
                "model_family": "facebook/dinov2-small",
                "experiment": "E3",
                "selected_epoch": 10,
                "artifact_included_in_pack": False,
                "serving_endpoint_included_in_pack": False,
            },
            "task": "BINARY_ANY_DEFECT_CLASSIFICATION",
            "decision_boundary": {
                "threshold": 0.8984375,
                "below_threshold": "NOT_NORMAL",
                "advisory_only": True,
                "automatic_decision_allowed": False,
            },
            "capabilities": {
                "defect_type": False,
                "defect_location": False,
                "bounding_box": False,
            },
            "held_out_test": {
                "image_count": 10067,
                "ap_any_defect": 0.884863,
                "auroc": 0.931604,
                "threshold_metrics": {"precision": 0.954333, "recall": 0.508422},
                "prediction_sha256": "a" * 64,
            },
            "recommended_slice": {
                "material": "plastic_hard",
                "defect_slices": [
                    {"kaputt_label": "deconstruction"},
                    {"kaputt_label": "actuation"},
                ],
            },
            "product_domain_status": "NOT_EVALUATED",
            "report_metrics_reproduced_by_csight": False,
            "qualification_status": "SUPPLIED_OFFLINE_REPORT_WITH_LIMITATIONS",
            "forbidden_claims": [
                "PRODUCT_SPECIFIC_ACCURACY",
                "ACTUAL_CUSTOMER_PERFORMANCE",
                "AUTOMATED_NORMAL_DECISION",
                "AUTOMATED_REFUND_OR_EXCHANGE",
                "ROI_OR_COST_SAVINGS",
                "DEFECT_TYPE_OR_LOCATION_FROM_BINARY_SCORE",
            ],
            "runtime_integration_status": "AVAILABLE" if runtime_available else "NOT_AVAILABLE",
            "checkpoint_package_status": "AVAILABLE" if runtime_available else "NOT_AVAILABLE",
            "endpoint_ref": "private-runtime-reference" if runtime_available else None,
        },
    )
    artifact_hashes = {filename: _sha256(path / filename) for filename in ARTIFACTS}
    _dump_json(
        path / "manifest.json",
        {
            "schema_version": "scenario_poc_pack/1.0.0",
            "dataset_name": "scenario_poc_hard_plastic_v1",
            "dataset_version": "1.0.0",
            "source_type": "SYNTHETIC_REFERENCE",
            "claims_boundary": dict(SAFE_CLAIMS_BOUNDARY),
            "record_count": 30,
            "split_counts": {"demo": 5, "evaluation": 25},
            "demo_scenario_ids": [f"DEMO-{index}" for index in range(1, 6)],
            "source_reports": ["vision-model-report", "poc-item-recommendation"],
            "artifact_hashes": artifact_hashes,
            "pack_hash": _canonical_hash(dict(sorted(artifact_hashes.items()))),
        },
    )
    return path


def test_offline_pack_can_be_ready_while_runtime_vision_is_blocked(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")

    assessment = assess_scenario_poc(pack)

    assert assessment.verdict is ScenarioPocVerdict.READY
    assert assessment.offline_status is OfflinePackStatus.READY
    assert assessment.offline_failures == ()
    assert assessment.runtime_status is RuntimeVisionStatus.BLOCKED
    assert assessment.runtime_blockers == (
        "VISION_ENDPOINT_NOT_AVAILABLE",
        "VISION_CHECKPOINT_PACKAGE_NOT_AVAILABLE",
        "VISION_ENDPOINT_REFERENCE_MISSING",
        "VISION_RUNTIME_PROBE_NOT_EXECUTED",
    )


def test_tampered_artifact_blocks_offline_verdict(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    with (pack / "cases.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")

    assessment = assess_scenario_poc(pack)

    assert assessment.verdict is ScenarioPocVerdict.BLOCKED
    assert "artifact_and_pack_hashes" in assessment.offline_failures
    assert "minimum_30_unique_cases" in assessment.offline_failures


def test_incomplete_gold_and_missing_demo_boundary_fail_closed(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    gold = [json.loads(line) for line in (pack / "gold.jsonl").read_text().splitlines()]
    del gold[0]["expected"]["resolution"]
    _dump_jsonl(pack / "gold.jsonl", gold)
    demos = json.loads((pack / "demo_scenarios.json").read_text())
    demos["scenarios"][4]["boundary"] = "UNRECOGNIZED_BOUNDARY"
    _dump_json(pack / "demo_scenarios.json", demos)
    _reseal_manifest(pack)

    assessment = assess_scenario_poc(pack)

    assert "gold_complete_and_case_linked" in assessment.offline_failures
    assert "five_demo_safety_boundaries" in assessment.offline_failures


def test_offline_runner_never_promotes_runtime_from_manifest_declarations(
    tmp_path: Path,
) -> None:
    pack = _make_pack(tmp_path / "pack", runtime_available=True)

    assessment = assess_scenario_poc(pack)

    assert assessment.verdict is ScenarioPocVerdict.READY
    assert assessment.runtime_status is RuntimeVisionStatus.BLOCKED
    assert assessment.runtime_blockers == ("VISION_RUNTIME_PROBE_NOT_EXECUTED",)


def test_unsafe_manifest_claim_boundary_blocks_offline_verdict(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    manifest = json.loads((pack / "manifest.json").read_text())
    manifest["claims_boundary"]["actual_performance_or_roi_claim_allowed"] = True
    manifest["claims_boundary"]["verdict"] = "LIMITED_POC"
    _dump_json(pack / "manifest.json", manifest)

    assessment = assess_scenario_poc(pack)

    assert "synthetic_claim_boundary" in assessment.offline_failures


def test_low_score_normal_interpretation_blocks_offline_verdict(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    gold = [json.loads(line) for line in (pack / "gold.jsonl").read_text().splitlines()]
    vision = cast(dict[str, object], cast(dict[str, object], gold[2]["expected"])["vision"])
    vision["business_interpretation"] = "NORMAL"
    _dump_jsonl(pack / "gold.jsonl", gold)
    _reseal_manifest(pack)

    assessment = assess_scenario_poc(pack)

    assert "gold_complete_and_case_linked" in assessment.offline_failures


def test_invalid_policy_effective_date_blocks_offline_verdict(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    policy = json.loads((pack / "policy.json").read_text())
    policy["document"]["effective_from"] = "not-a-date"
    _dump_json(pack / "policy.json", policy)
    _reseal_manifest(pack)

    assessment = assess_scenario_poc(pack)

    assert "versioned_effective_synthetic_policy" in assessment.offline_failures


def test_unsafe_binary_model_semantics_block_offline_verdict(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    model = json.loads((pack / "model_manifest.json").read_text())
    model["decision_boundary"]["below_threshold"] = "NORMAL"
    model["capabilities"]["defect_type"] = True
    _dump_json(pack / "model_manifest.json", model)
    _reseal_manifest(pack)

    assessment = assess_scenario_poc(pack)

    assert "report_based_binary_model_manifest" in assessment.offline_failures


def test_machine_readable_report_is_sealed_and_has_no_host_path(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "secret-host-layout" / "pack")
    assessment = assess_scenario_poc(pack)
    report = build_acceptance_report(
        assessment,
        pack,
        evaluated_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )

    valid, failures = validate_acceptance_report(report)

    assert valid is True
    assert failures == ()
    assert report["verdict"] == "SCENARIO_TECH_POC_READY"
    assert report["runtime_status"] == "RUNTIME_VISION_INTEGRATION_BLOCKED"
    assert report["evaluated_at"] == "2026-08-27T12:00:00+00:00"
    assert "/secret-host-layout/" not in json.dumps(report)
    evidence = report["evidence_summary"]
    assert isinstance(evidence, dict)
    assert evidence["observed_record_count"] == 30
    assert evidence["observed_demo_scenario_count"] == 5


def test_report_hash_tampering_is_detected(tmp_path: Path) -> None:
    pack = _make_pack(tmp_path / "pack")
    report = build_acceptance_report(assess_scenario_poc(pack), pack)
    evidence = report["evidence_summary"]
    assert isinstance(evidence, dict)
    evidence["observed_record_count"] = 31

    valid, failures = validate_acceptance_report(report)

    assert valid is False
    assert "REPORT_HASH_MISMATCH" in failures
