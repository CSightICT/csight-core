"""Additive GGUF matrix parsing, provenance gates, and immutable v1 compatibility."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.model_activation import ModelReleaseStatus, ModelReleaseTask
from app.platform.qwen4090_gguf import (
    CandidateReleaseStatusV2,
    Qwen4090CandidateMatrixV2,
    assess_gguf_matrix,
)
from scripts.verify_qwen4090_candidates import CandidateMatrixError, load_matrix
from scripts.verify_qwen4090_gguf_candidates import (
    DEFAULT_DATASET,
    DEFAULT_LEGACY_MATRIX,
    DEFAULT_MATRIX,
    build_report,
    load_gguf_matrix,
    verify_inputs,
)
from tests.unit.test_model_activation_gguf import gguf_manifest_fixture

pytestmark = pytest.mark.unit


def test_v2_matrix_is_additive_and_preserves_exact_v1_baseline() -> None:
    matrix = load_gguf_matrix(DEFAULT_MATRIX)
    verify_inputs(
        matrix,
        dataset_path=DEFAULT_DATASET,
        legacy_matrix_path=DEFAULT_LEGACY_MATRIX,
    )
    report = build_report(matrix)

    assert matrix.schema_version == "qwen4090_candidate_matrix/2.0.0"
    assert matrix.legacy_baseline.matrix_digest == (
        "sha256:8b01bc03c29a7f64cb6ffcfc4adaa232ccb7cf910ad39020c0daa82c413386b1"
    )
    assert report["release_status"] == "NO_RELEASE_ELIGIBLE"
    assert all(
        item.status is CandidateReleaseStatusV2.PENDING_QUALIFICATION
        for item in assess_gguf_matrix(matrix)
    )
    assert all(
        "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED" in item.reason_codes
        for item in assess_gguf_matrix(matrix)
    )


def test_v1_and_v2_parsers_do_not_accept_each_others_contracts() -> None:
    with pytest.raises(CandidateMatrixError):
        load_matrix(DEFAULT_MATRIX)
    with pytest.raises(ValidationError):
        Qwen4090CandidateMatrixV2.model_validate_json(DEFAULT_LEGACY_MATRIX.read_bytes())


def test_personal_owner_gguf_cannot_be_release_eligible() -> None:
    eligible = gguf_manifest_fixture(
        ModelReleaseStatus.RELEASE_ELIGIBLE,
        ModelReleaseTask.POLICY_QUERY_BUILDER_V1,
    )
    with pytest.raises(ValidationError, match="organization mirror"):
        eligible.model_copy(
            update={"artifact": "doongdoongdoong/csight-qwen3.8-27b-gguf"}
        ).__class__.model_validate(
            {
                **eligible.model_dump(mode="python"),
                "artifact": "doongdoongdoong/csight-qwen3.8-27b-gguf",
            }
        )


def test_v2_matrix_file_is_bounded_regular_json() -> None:
    assert isinstance(DEFAULT_MATRIX, Path)
    assert DEFAULT_MATRIX.is_file() and not DEFAULT_MATRIX.is_symlink()
    assert DEFAULT_MATRIX.stat().st_size < 1024 * 1024
