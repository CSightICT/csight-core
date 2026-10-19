"""Exercise diagnostic alignment at the existing canonical text/vision boundary."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.product_defect_cs.evidence_alignment import (
    AlignmentInput,
    AlignmentReport,
    AlignmentStatus,
    EvidenceRequest,
    Reason,
    align_evidence,
    canonical_digest,
)
from app.platform.analysis.enums import ExtractionIssueType
from app.platform.analysis.errors import LLMSourceQuoteMismatchError
from scripts.engine_alignment_fixtures import ContractCase, make_input
from scripts.evaluate_engine_alignment import DEFAULT_DATASET, evaluate_dataset, write_new_report

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ContractCase.model_validate_json(line) for line in DEFAULT_DATASET.read_bytes().splitlines()
]


def _input() -> AlignmentInput:
    return make_input(CASES[0])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_synthetic_contract_scenarios(case: ContractCase) -> None:
    value = make_input(case)
    before = value.model_dump_json()
    result = align_evidence(value)
    assert tuple(c.status for c in result.claims) == case.expected
    assert set(case.required_reasons) <= {r for c in result.claims for r in c.reasons}
    assert result == align_evidence(value)
    assert value.model_dump_json() == before
    assert result.advisory_only and result.human_review_required
    assert not result.policy_eligible and not result.model_quality_qualified
    assert all(not c.location_verified for c in result.claims)


@pytest.mark.parametrize("branch", ["text", "snapshot", "vision"])
@pytest.mark.parametrize("key", ["tenant_id", "analysis_run_id"])
def test_foreign_sources_rejected(branch: str, key: str) -> None:
    value = _input().model_dump(mode="json")
    node = (
        value["text"]["record"]
        if branch == "text"
        else value["snapshots"][0]
        if branch == "snapshot"
        else value["vision"][0]["record"]
    )
    node[key] = "foreign"
    with pytest.raises(ValidationError, match="ALIGNMENT_SCOPE_MISMATCH"):
        AlignmentInput.model_validate(value)


@pytest.mark.parametrize(
    "kind",
    [
        "snapshot",
        "position",
        "result",
        "detection",
        "sha",
        "unsnapshotted",
        "image_ref",
        "stage",
        "claims",
        "quote",
    ],
)
def test_binding_and_integrity_fail_closed(kind: str) -> None:
    value = _input().model_dump(mode="json")
    if kind == "snapshot":
        value["snapshots"].append(value["snapshots"][0])
    elif kind == "position":
        value["snapshots"][0]["position"] = 2
    elif kind == "result":
        value["vision"].append(value["vision"][0])
    elif kind == "detection":
        detections = value["vision"][0]["record"]["result"]["detections"]
        detections.append(detections[0])
    elif kind == "sha":
        value["vision"][0]["evidence_sha256"] = "f" * 64
    elif kind == "unsnapshotted":
        value["vision"][0]["record"]["evidence_id"] = "not-in-snapshot"
    elif kind == "image_ref":
        value["vision"][0]["record"]["result"]["image_reference"] = "foreign-image"
    elif kind == "stage":
        value["vision"][0]["record"]["stage_run_id"] = value["text"]["record"]["stage_run_id"]
    elif kind == "claims":
        value["text"]["record"]["result"]["issue_types"].append("DENT")
    else:
        value["text"]["record"]["result"]["claims"][0]["source_quote"] = "fabricated"
    with pytest.raises((ValidationError, LLMSourceQuoteMismatchError)):
        align_evidence(AlignmentInput.model_validate(value))


def test_unchecked_model_copy_cannot_bypass_validation() -> None:
    corrupted = _input().model_copy(update={"tenant_id": "foreign"})
    with pytest.raises(ValidationError, match="ALIGNMENT_SCOPE_MISMATCH"):
        align_evidence(corrupted)


def test_input_digest_changes_for_prompt_runtime_and_threshold() -> None:
    value = _input()
    original = align_evidence(value)
    for text in (
        value.text.model_copy(update={"runtime_sha256": "e" * 64}),
        value.text.model_copy(update={"prompt_sha256": "e" * 64}),
    ):
        assert (
            align_evidence(value.model_copy(update={"text": text})).input_sha256
            != original.input_sha256
        )
    changed = value.model_copy(
        update={"profile": value.profile.model_copy(update={"detection_min_score": 0.95})}
    )
    other = align_evidence(changed)
    assert other.profile_sha256 != original.profile_sha256
    assert other.input_sha256 != original.input_sha256
    assert other.claims[0].status is AlignmentStatus.UNRESOLVED


def test_report_omits_prose_and_provider_request_identifier() -> None:
    value = _input()
    marker = "PRIVATE-CUSTOMER-CONTENT-AND-INSTRUCTIONS"
    raw = value.model_dump(mode="json")
    raw["text"]["request"]["customer_message"] = marker
    raw["text"]["record"]["result"]["summary"] = marker
    raw["text"]["record"]["result"]["claims"][0]["source_quote"] = marker
    raw["text"]["record"]["result"]["claims"][0]["description"] = marker
    raw["text"]["metadata"]["provider_request_id"] = marker
    report = align_evidence(AlignmentInput.model_validate(raw))
    serialized = report.model_dump_json()
    assert marker not in serialized
    assert "source_quote" not in serialized
    assert "summary" not in serialized
    assert report.sources[0].prompt_sha256 == value.text.prompt_sha256
    assert report.sources[1].evidence_sha256 == value.snapshots[0].sha256
    assert report.sources[1].result_sha256 == canonical_digest(value.vision[0].record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("human_review_required", False),
        ("advisory_only", False),
        ("policy_eligible", True),
        ("model_quality_qualified", True),
        ("approve_refund", True),
    ],
)
def test_report_cannot_represent_automatic_decision(field: str, value: bool) -> None:
    raw = align_evidence(_input()).model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        AlignmentReport.model_validate(raw)


def test_claims_are_preserved_individually_with_candidate_provenance() -> None:
    value = _input()
    first = value.text.record.result.claims[0]
    second = first.model_copy(update={"type": ExtractionIssueType.LEAKAGE})
    result = value.text.record.result.model_copy(
        update={
            "claims": (first, second),
            "issue_types": (ExtractionIssueType.CRACK, ExtractionIssueType.LEAKAGE),
        }
    )
    text = value.text.model_copy(
        update={"record": value.text.record.model_copy(update={"result": result})}
    )
    report = align_evidence(value.model_copy(update={"text": text}))
    assert [c.claim_index for c in report.claims] == [0, 1]
    assert report.claims[0].candidates[0].vision_result_id == value.vision[0].record.id
    assert report.claims[1].candidates == ()
    assert EvidenceRequest.PROVIDE_REFERENCE_OR_DETAILS in report.claims[1].evidence_requests


def test_all_missing_sources_stay_visible() -> None:
    value = _input().model_copy(update={"vision": ()})
    report = align_evidence(value)
    assert report.expected_image_count == 1
    assert report.observed_image_count == 0
    assert report.missing_evidence_ids == (value.snapshots[0].evidence_id,)
    assert Reason.VISION_RESULT_MISSING in report.claims[0].reasons


def test_one_stage_cannot_mix_vision_models_or_threshold_versions() -> None:
    case = next(c for c in CASES if c.id == "multiple-images-repeated-type")
    for key in ("model_revision", "threshold_version"):
        raw = make_input(case).model_dump(mode="json")
        raw["vision"][1]["record"]["result"][key] = "changed"
        with pytest.raises(ValidationError, match="ALIGNMENT_MIXED_VISION_IDENTITY"):
            AlignmentInput.model_validate(raw)


def test_schema_limits_unbounded_arrays_and_non_finite_thresholds() -> None:
    raw = _input().model_dump(mode="json")
    raw["snapshots"] *= 21
    with pytest.raises(ValidationError):
        AlignmentInput.model_validate(raw)
    for invalid in (float("nan"), float("inf"), -0.1, 1.1):
        raw = _input().model_dump(mode="json")
        raw["profile"]["detection_min_score"] = invalid
        with pytest.raises(ValidationError):
            AlignmentInput.model_validate(raw)


def test_no_claims_does_not_invent_normal_or_confirmed_outcome() -> None:
    value = _input()
    result = value.text.record.result.model_copy(update={"claims": (), "issue_types": ()})
    record = value.text.record.model_copy(update={"result": result})
    report = align_evidence(
        value.model_copy(update={"text": value.text.model_copy(update={"record": record})})
    )
    assert report.claims == ()
    assert report.human_review_required and not report.policy_eligible


def test_dataset_failure_is_not_reported_as_success(tmp_path: Path) -> None:
    case = CASES[0].model_dump(mode="json")
    case["expected"] = ["UNRESOLVED"]
    path = tmp_path / "wrong-gold.jsonl"
    path.write_text(json.dumps(case) + "\n")
    report = evaluate_dataset(path)
    assert report["status"] == "FAIL" and report["failed"] == 1
    assert report["model_quality"] == "NOT_RUN"


def test_contract_dataset_is_explicitly_not_model_evaluation() -> None:
    report = evaluate_dataset(DEFAULT_DATASET)
    assert report["passed"] == len(CASES)
    assert report["evaluation_scope"] == "SYNTHETIC_CANONICAL_CONTRACT_ONLY"
    assert report["model_quality"] == report["combined_model_gain"] == "NOT_RUN"


def test_owner_only_report_cannot_overwrite_previous_run(tmp_path: Path) -> None:
    path = tmp_path / "run"
    payload: dict[str, Any] = {"status": "PASS"}
    write_new_report(path, payload)
    assert path.stat().st_mode & 0o777 == 0o700
    assert (path / "result.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_new_report(path, {"status": "FAIL"})
    assert json.loads((path / "result.json").read_text()) == payload


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_engine_alignment", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_cli_replays_canonical_input_and_returns_compact_result(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(_input().model_dump_json())
    output = tmp_path / "run"
    proc = _cli("replay", "--input", str(input_path), "--output-dir", str(output))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "PASS"
    parsed = AlignmentReport.model_validate_json((output / "result.json").read_text())
    assert parsed == align_evidence(_input())


def test_cli_rejects_private_invalid_input_without_echoing_values(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"private": "SECRET-SYNTHETIC-MARKER"}')
    output = tmp_path / "run"
    proc = _cli("replay", "--input", str(path), "--output-dir", str(output))
    assert proc.returncode == 2
    assert "SECRET-SYNTHETIC-MARKER" not in proc.stdout + proc.stderr
    assert "Traceback" not in proc.stdout + proc.stderr
    assert not output.exists()
