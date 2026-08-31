"""Fail-closed RTX 4090 Qwen candidate qualification tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.qwen4090_release import (
    CandidateReleaseStatus,
    Qwen4090Candidate,
    Qwen4090CandidateMatrix,
    assess_candidate,
    assess_matrix,
)
from scripts.verify_qwen4090_candidates import CandidateMatrixError, verify_dataset

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v1.json"
SHA = "sha256:" + "a" * 64


def _matrix() -> Qwen4090CandidateMatrix:
    return Qwen4090CandidateMatrix.model_validate_json(MATRIX_PATH.read_bytes())


def _release_eligible_candidate(matrix: Qwen4090CandidateMatrix) -> Qwen4090Candidate:
    source = matrix.candidates[2].model_dump(mode="python")
    source["candidate_id"] = "qwen38-27b-w4a16-csight-qualified"
    source["artifact"] |= {
        "source": "OFFICIAL_QWEN",
        "artifact_content_digest": SHA,
        "quantization_recipe_digest": SHA,
        "calibration_dataset_digest": SHA,
    }
    source["serving"] |= {
        "dependency_lock_digest": SHA,
        "sbom_digest": SHA,
        "gpu_memory_utilization": 0.88,
    }
    source["qualification"] |= {
        "dataset_version": matrix.qualification_dataset_version,
        "dataset_digest": matrix.qualification_dataset_digest,
        "result_digest": SHA,
        "evaluation_contract_unambiguous": True,
        "workflow_cases": 20,
        "terminal_workflow_cases": 20,
        "requested_action_set_f1": 0.9,
        "requested_action_exact_accuracy": 0.85,
        "system_missing_exact_accuracy": 0.98,
        "action_consistency_accuracy": 0.95,
        "text_ambiguity_set_f1": 0.75,
        "observed_min_free_vram_mib": 2048,
        "measured_at": "2026-08-30T00:00:00Z",
    }
    return Qwen4090Candidate.model_validate(source)


def _assess(
    matrix: Qwen4090CandidateMatrix,
    candidate: Qwen4090Candidate,
):
    return assess_candidate(
        candidate,
        target_gpu_name=matrix.target_gpu_name,
        qualification_dataset_version=matrix.qualification_dataset_version,
        qualification_dataset_digest=matrix.qualification_dataset_digest,
        thresholds=matrix.thresholds,
    )


def test_frozen_candidate_matrix_is_fail_closed() -> None:
    assessments = {item.candidate_id: item for item in assess_matrix(_matrix())}

    assert assessments["qwen38-27b-bf16-official-preflight"].status is (
        CandidateReleaseStatus.HARDWARE_EXCLUDED
    )
    assert assessments["qwen38-27b-fp8-official-preflight"].reason_codes == (
        "WEIGHTS_EXCEED_DEVICE_VRAM",
    )

    baseline = assessments["qwen38-27b-awq-int4-community-vllm026"]
    assert baseline.status is CandidateReleaseStatus.SHADOW_ONLY
    assert {
        "QUALIFICATION_DATASET_VERSION_MISMATCH",
        "EVALUATION_CONTRACT_AMBIGUOUS",
        "WORKFLOW_TERMINAL_GATE_FAILED",
        "VRAM_HEADROOM_BELOW_MINIMUM",
        "REQUESTED_ACTION_SET_F1_NOT_RECORDED",
    }.issubset(baseline.reason_codes)

    assert assessments["qwen38-27b-awq-int4-community-vllm028"].status is (
        CandidateReleaseStatus.PENDING_QUALIFICATION
    )
    assert assessments["qwen3-8b-fp8-official-vllm026"].status is (
        CandidateReleaseStatus.PENDING_QUALIFICATION
    )


def test_complete_evidence_can_become_release_eligible() -> None:
    matrix = _matrix()

    assessment = _assess(matrix, _release_eligible_candidate(matrix))

    assert assessment.status is CandidateReleaseStatus.RELEASE_ELIGIBLE
    assert assessment.reason_codes == ()


def test_official_dynamic_fp8_does_not_invent_a_calibration_dataset() -> None:
    matrix = _matrix()
    candidate = _release_eligible_candidate(matrix).model_dump(mode="python")
    candidate["artifact"] |= {
        "source": "OFFICIAL_QWEN",
        "quantization_format": "FP8_W8A8_BLOCK128_SAFE_TENSORS",
        "calibration_evidence_mode": "OFFICIAL_PREQUANTIZED_DYNAMIC_FP8",
        "calibration_dataset_digest": None,
    }

    assessment = _assess(matrix, Qwen4090Candidate.model_validate(candidate))

    assert assessment.status is CandidateReleaseStatus.RELEASE_ELIGIBLE
    assert "CALIBRATION_DATASET_UNPINNED" not in assessment.reason_codes


def test_community_artifact_cannot_claim_official_dynamic_fp8_exemption() -> None:
    candidate = _matrix().candidates[2].model_dump(mode="python")
    candidate["artifact"] |= {
        "quantization_format": "FP8_W8A8_BLOCK128_SAFE_TENSORS",
        "calibration_evidence_mode": "OFFICIAL_PREQUANTIZED_DYNAMIC_FP8",
    }

    with pytest.raises(ValidationError, match="official FP8 artifact"):
        Qwen4090Candidate.model_validate(candidate)


@pytest.mark.parametrize(
    ("section", "updates", "reason"),
    [
        (
            "serving",
            {"automatic_cross_model_fallback": True},
            "AUTOMATIC_CROSS_MODEL_FALLBACK_ENABLED",
        ),
        ("qualification", {"measured_gpu_name": "NVIDIA A100"}, "WRONG_HARDWARE_PROFILE"),
    ],
)
def test_unsafe_serving_or_wrong_hardware_stays_shadow_only(
    section: str,
    updates: dict[str, object],
    reason: str,
) -> None:
    matrix = _matrix()
    candidate = _release_eligible_candidate(matrix).model_dump(mode="python")
    candidate[section] |= updates

    assessment = _assess(matrix, Qwen4090Candidate.model_validate(candidate))

    assert assessment.status is CandidateReleaseStatus.SHADOW_ONLY
    assert reason in assessment.reason_codes


def test_matrix_requires_unique_ids_and_exactly_one_baseline() -> None:
    matrix = _matrix().model_dump(mode="python")
    matrix["candidates"][1]["candidate_id"] = matrix["candidates"][0]["candidate_id"]
    with pytest.raises(ValidationError, match="candidate ids must be unique"):
        Qwen4090CandidateMatrix.model_validate(matrix)

    matrix = _matrix().model_dump(mode="python")
    matrix["candidates"][2]["role"] = "MODEL_CHALLENGER"
    with pytest.raises(ValidationError, match="exactly one baseline"):
        Qwen4090CandidateMatrix.model_validate(matrix)


def test_verifier_detects_qualification_dataset_drift(tmp_path: Path) -> None:
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text("drifted\n", encoding="utf-8")
    expected = "sha256:" + hashlib.sha256(b"expected\n").hexdigest()
    matrix = _matrix().model_copy(update={"qualification_dataset_digest": expected})

    with pytest.raises(CandidateMatrixError, match="digest drifted"):
        verify_dataset(matrix, dataset)
