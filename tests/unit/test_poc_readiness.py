"""Evidence-backed Limited PoC promotion gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform.poc_readiness import PocVerdict, assess_poc_readiness

pytestmark = pytest.mark.unit


def _qualified_manifest() -> dict[str, object]:
    return {
        "customer_scope": {
            "customer_candidate_confirmed": True,
            "product_category": "appliance",
            "defect_types": ["crack", "leak"],
            "evidence_ref": "registry://scope/1",
        },
        "real_case_dataset": {
            "deidentified": True,
            "case_count": 30,
            "gold_reviewed_count": 30,
            "evidence_ref": "registry://cases/1",
        },
        "real_policy_corpus": {
            "actual_company_policy": True,
            "versioned": True,
            "effective_dates_present": True,
            "evidence_ref": "registry://policy/1",
        },
        "privacy_and_access": {
            "retention_approved": True,
            "deletion_approved": True,
            "exif_removal_approved": True,
            "access_control_approved": True,
            "evidence_ref": "registry://privacy/1",
        },
        "vision_scope": {
            "status": "EXPLICITLY_EXCLUDED",
            "exclusion_scope_documented": True,
            "manifest_complete": False,
            "per_defect_evaluation_complete": False,
            "evidence_ref": "registry://vision/1",
        },
        "qwen_re_evaluation": {
            "extraction_status": "QUALIFIED_WITH_LIMITATIONS",
            "grounding_status": "QUALIFIED_WITH_LIMITATIONS",
            "evidence_ref": "registry://qwen/1",
        },
        "real_distribution_evaluation": {
            "policy": True,
            "cases": True,
            "user_queries": True,
            "evidence_ref": "registry://distribution/1",
        },
        "shadow_mode": {
            "completed": True,
            "human_gold_present": True,
            "comparable_decision_count": 20,
            "evidence_ref": "registry://shadow/1",
        },
        "safety_regression": {
            "cross_tenant": 0,
            "unauthorized_decision": 0,
            "duplicate_intent": 0,
            "duplicate_result": 0,
            "live_execution": 0,
            "parameter_inference": 0,
            "premature_closure": 0,
            "decision_mutation": 0,
            "evidence_ref": "registry://safety/1",
        },
        "clean_environment_regression": {
            "backend": "PASS",
            "frontend": "PASS",
            "clean_environment_demo": "PASS",
            "evidence_ref": "registry://regression/1",
        },
    }


def test_all_evidenced_gates_allow_limited_poc() -> None:
    assessment = assess_poc_readiness(_qualified_manifest())
    assert assessment.verdict is PocVerdict.LIMITED_POC
    assert assessment.failures == ()


def test_missing_evidence_never_inherits_a_pass() -> None:
    manifest = _qualified_manifest()
    privacy = manifest["privacy_and_access"]
    assert isinstance(privacy, dict)
    privacy["evidence_ref"] = None
    assessment = assess_poc_readiness(manifest)
    assert assessment.verdict is PocVerdict.SYNTHETIC_MOCK_SIMULATION_DEMO
    assert "privacy_retention_exif_access_approval" in assessment.failures


def test_unknown_safety_counts_never_count_as_zero() -> None:
    manifest = _qualified_manifest()
    safety = manifest["safety_regression"]
    assert isinstance(safety, dict)
    safety["duplicate_intent"] = None
    assessment = assess_poc_readiness(manifest)
    assert "zero_safety_violations" in assessment.failures


def test_checked_in_current_state_is_explicitly_simulation_only() -> None:
    path = Path(__file__).resolve().parents[2] / "evaluation/poc_readiness/current_gate.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assessment = assess_poc_readiness(manifest)
    assert assessment.verdict is PocVerdict.SYNTHETIC_MOCK_SIMULATION_DEMO
    assert assessment.failures
