from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.seed_realistic_poc_demo import (
    BOUNDARY_COUNT_KEYS,
    DEFAULT_MANIFEST,
    DEFECT_RANKS,
    NORMAL_REFERENCE_RANKS,
    DemoManifest,
    RealisticDemoSeedFailure,
    ResolvedDemoSource,
    build_case_attributes,
    ensure_private_evidence,
    load_manifest,
    require_local_runtime,
    validate_boundary_preservation,
    validate_core_vision_result,
    validate_private_evidence_object,
)


@pytest.mark.unit
def test_committed_manifest_freezes_realistic_6_to_4_selection_and_boundaries() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)

    assert manifest.tenant_slug == "csight"
    assert manifest.selection.ratio == "6:4"
    assert manifest.selection.defect_ranks == DEFECT_RANKS
    assert manifest.selection.normal_reference_ranks == NORMAL_REFERENCE_RANKS
    assert len(manifest.cases) == 10
    assert len({item.case_input.customer_message for item in manifest.cases}) == 10
    assert manifest.boundaries.policy_input_linkage == "NOT_LINKED_TO_POLICY_INPUT"
    assert manifest.boundaries.final_decision_owner == "AUTHENTICATED_HUMAN_ONLY"
    assert manifest.boundaries.normal_confirmation_supported is False
    assert {item.source.source_grade for item in manifest.cases} == {
        "KAPUTT_SELECTED_CORRECT_POSITIVE",
        "USER_SUPPLIED_NORMAL_REFERENCE",
    }
    assert {item.source.rights_status for item in manifest.cases} == {
        "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED"
    }


@pytest.mark.unit
def test_manifest_rejects_normal_reference_as_confirmed_normal() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    normal_case = payload["cases"][6]
    normal_case["source"]["expected_e3_outcome"] = "HIGH_CONFIDENCE_DEFECT_CANDIDATE"

    with pytest.raises(ValidationError, match="source grade, outcome, and selection bias"):
        DemoManifest.model_validate(payload)


@pytest.mark.unit
def test_case_attributes_expose_one_fixed_ui_provenance_contract(tmp_path: Path) -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    definition = manifest.cases[0]
    source = ResolvedDemoSource(
        definition=definition,
        path=tmp_path / "unused.jpg",
        capture_id="capture",
        image_sha256=definition.source.image_sha256,
        source_metadata={},
    )

    attributes = build_case_attributes(manifest, source)
    provenance = attributes["realistic_demo"]

    assert "realistic_internal_demo" not in attributes
    assert isinstance(provenance, dict)
    assert provenance["schema_version"] == "1.0"
    assert provenance["scenario_scope"] == "INTERNAL_CURATED_6_DEFECT_4_BELOW_THRESHOLD"
    assert provenance["source_grade"] == "KAPUTT_SELECTED_CORRECT_POSITIVE"
    assert provenance["rights_status"] == "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED"
    assert provenance["policy_input_linkage"] == "NOT_LINKED_TO_POLICY_INPUT"


@pytest.mark.unit
def test_existing_workflow_counts_may_be_preserved_on_idempotent_replay() -> None:
    counts = {key: 0 for key in BOUNDARY_COUNT_KEYS}
    counts["policy_retrieval_runs"] = 1
    counts["human_review_tasks"] = 1
    counts["human_review_decisions"] = 1

    validate_boundary_preservation(before=counts, after=dict(counts), newly_created=False)


@pytest.mark.unit
def test_seed_rejects_new_or_increased_workflow_rows() -> None:
    zero = {key: 0 for key in BOUNDARY_COUNT_KEYS}
    nonzero = dict(zero)
    nonzero["human_review_decisions"] = 1

    with pytest.raises(RealisticDemoSeedFailure, match="newly created"):
        validate_boundary_preservation(before=nonzero, after=nonzero, newly_created=True)
    with pytest.raises(RealisticDemoSeedFailure, match="changed"):
        validate_boundary_preservation(before=zero, after=nonzero, newly_created=False)


@pytest.mark.unit
def test_local_runtime_guard_accepts_only_loopback_local_or_test() -> None:
    core, vision = require_local_runtime(
        environment="local",
        database_url="postgresql+psycopg://user:secret@127.0.0.1:5432/csight",
        core_base_url="http://localhost:8000/",
        vision_base_url="http://127.0.0.1:8093",
    )

    assert core == "http://localhost:8000"
    assert vision == "http://127.0.0.1:8093"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("environment", "database_url", "core_url", "vision_url"),
    (
        (
            "production",
            "postgresql+psycopg://user:secret@127.0.0.1:5432/csight",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8093",
        ),
        (
            "local",
            "postgresql+psycopg://user:secret@db.internal:5432/csight",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8093",
        ),
        (
            "test",
            "postgresql+psycopg://user:secret@localhost:5432/csight",
            "http://localhost.evil:8000",
            "http://127.0.0.1:8093",
        ),
        (
            "test",
            "postgresql+psycopg://user:secret@localhost:5432/csight",
            "http://127.0.0.1:8000",
            "https://127.0.0.1:8093",
        ),
    ),
)
def test_local_runtime_guard_rejects_nonlocal_targets(
    environment: str,
    database_url: str,
    core_url: str,
    vision_url: str,
) -> None:
    with pytest.raises(RealisticDemoSeedFailure):
        require_local_runtime(
            environment=environment,
            database_url=database_url,
            core_base_url=core_url,
            vision_base_url=vision_url,
        )


def _core_result(*, score: float, outcome: str) -> Mapping[str, object]:
    return {
        "provider_name": "remote_vision",
        "model_name": "csight-dinov2-vits14-kaputt-binary",
        "model_version": "e3-epoch10-20260827",
        "model_revision": "49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e",
        "taxonomy_version": "csight-any-defect-assessment-v1",
        "threshold_version": "1.0",
        "preprocess_version": "1.0",
        "postprocess_version": "sigmoid-any-defect-v1",
        "detections": [],
        "image_assessment": {
            "assessment_type": "ANY_DEFECT",
            "score": score,
            "threshold": 0.8984375,
            "threshold_operator": "GREATER_THAN_OR_EQUAL",
            "outcome": outcome,
        },
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "outcome"),
    (
        (0.99, "HIGH_CONFIDENCE_DEFECT_CANDIDATE"),
        (0.01, "BELOW_HIGH_CONFIDENCE_THRESHOLD"),
    ),
)
def test_core_result_preserves_nonlocalizing_binary_outcomes(score: float, outcome: str) -> None:
    actual_score, actual_outcome = validate_core_vision_result(
        _core_result(score=score, outcome=outcome),
        expected_outcome=outcome,
    )

    assert actual_score == score
    assert actual_outcome == outcome
    assert actual_outcome != "NORMAL"


@pytest.mark.unit
def test_core_result_rejects_detection_or_expected_outcome_drift() -> None:
    result = dict(_core_result(score=0.01, outcome="BELOW_HIGH_CONFIDENCE_THRESHOLD"))
    result["detections"] = [{"fabricated": True}]
    with pytest.raises(RealisticDemoSeedFailure, match="localized detections"):
        validate_core_vision_result(
            result,
            expected_outcome="BELOW_HIGH_CONFIDENCE_THRESHOLD",
        )

    with pytest.raises(RealisticDemoSeedFailure, match="outcome"):
        validate_core_vision_result(
            _core_result(score=0.01, outcome="BELOW_HIGH_CONFIDENCE_THRESHOLD"),
            expected_outcome="HIGH_CONFIDENCE_DEFECT_CANDIDATE",
        )


@pytest.mark.unit
def test_existing_matching_private_evidence_is_reused_without_upload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition = load_manifest(DEFAULT_MANIFEST).cases[0]
    source_path = tmp_path / "source.jpg"
    source_path.write_bytes(b"not-read-on-replay")
    source = ResolvedDemoSource(
        definition=definition,
        path=source_path,
        capture_id="capture",
        image_sha256=definition.source.image_sha256,
        source_metadata={},
    )

    def fake_json_request(**_: object) -> tuple[int, Mapping[str, object]]:
        return (
            200,
            {
                "items": [
                    {
                        "evidence_id": "evidence-1",
                        "sha256": definition.source.image_sha256,
                        "upload_status": "AVAILABLE",
                        "evidence_type": "IMAGE",
                    }
                ]
            },
        )

    def fail_upload(**_: object) -> Mapping[str, object]:
        raise AssertionError("matching Evidence must be reused")

    verified: list[str] = []

    def verify_content(**values: object) -> None:
        verified.append(str(values["evidence_id"]))

    monkeypatch.setattr("scripts.seed_realistic_poc_demo.json_request", fake_json_request)
    monkeypatch.setattr("scripts.seed_realistic_poc_demo._upload_private_evidence", fail_upload)
    monkeypatch.setattr(
        "scripts.seed_realistic_poc_demo.validate_private_evidence_object", verify_content
    )

    evidence, replayed = ensure_private_evidence(
        core_base_url="http://127.0.0.1:8000",
        case_id="case-1",
        source=source,
        authorization={"Authorization": "Bearer redacted"},
    )

    assert replayed is True
    assert evidence["evidence_id"] == "evidence-1"
    assert verified == ["evidence-1"]


@pytest.mark.unit
def test_authenticated_private_evidence_content_is_verified_against_frozen_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition = load_manifest(DEFAULT_MANIFEST).cases[0]
    source_path = tmp_path / "source.jpg"
    content = b"private-image"
    source_path.write_bytes(content)
    source = ResolvedDemoSource(
        definition=definition,
        path=source_path,
        capture_id="capture",
        image_sha256=hashlib.sha256(content).hexdigest(),
        source_metadata={},
    )

    def download_expected_content(**_: object) -> bytes:
        return content

    monkeypatch.setattr(
        "scripts.seed_realistic_poc_demo._download_private_evidence",
        download_expected_content,
    )
    validate_private_evidence_object(
        core_base_url="http://127.0.0.1:8000",
        case_id="case-1",
        evidence_id="evidence-1",
        source=source,
        authorization={"Authorization": "Bearer redacted"},
    )

    def download_corrupt_content(**_: object) -> bytes:
        return b"corrupt-image"

    monkeypatch.setattr(
        "scripts.seed_realistic_poc_demo._download_private_evidence",
        download_corrupt_content,
    )
    with pytest.raises(RealisticDemoSeedFailure, match="content does not match"):
        validate_private_evidence_object(
            core_base_url="http://127.0.0.1:8000",
            case_id="case-1",
            evidence_id="evidence-1",
            source=source,
            authorization={"Authorization": "Bearer redacted"},
        )


@pytest.mark.unit
def test_existing_mismatched_private_evidence_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition = load_manifest(DEFAULT_MANIFEST).cases[0]
    source = ResolvedDemoSource(
        definition=definition,
        path=tmp_path / "unused.jpg",
        capture_id="capture",
        image_sha256=definition.source.image_sha256,
        source_metadata={},
    )

    def fake_json_request(**_: object) -> tuple[int, Mapping[str, object]]:
        return (
            200,
            {
                "items": [
                    {
                        "evidence_id": "evidence-foreign",
                        "sha256": "f" * 64,
                        "upload_status": "AVAILABLE",
                        "evidence_type": "IMAGE",
                    }
                ]
            },
        )

    monkeypatch.setattr("scripts.seed_realistic_poc_demo.json_request", fake_json_request)

    with pytest.raises(RealisticDemoSeedFailure, match="does not match"):
        ensure_private_evidence(
            core_base_url="http://127.0.0.1:8000",
            case_id="case-1",
            source=source,
            authorization={"Authorization": "Bearer redacted"},
        )
