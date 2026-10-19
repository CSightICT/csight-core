"""Validate and assess the additive RTX 4090 GGUF/llama.cpp candidate matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.platform.qwen4090_gguf import (
    CandidateReleaseStatusV2,
    Qwen4090CandidateMatrixV2,
    assess_gguf_matrix,
)
from scripts.verify_qwen4090_candidates import load_matrix as load_legacy_matrix

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v2.json"
DEFAULT_LEGACY_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v1.json"
DEFAULT_DATASET = ROOT / "evaluation/llm_extraction_v2/gold.jsonl"
MAX_MATRIX_BYTES = 1024 * 1024


class GGUFCandidateMatrixError(RuntimeError):
    """The GGUF evidence is malformed, drifted, or not release eligible."""


def _regular_file(path: Path, *, maximum_bytes: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GGUFCandidateMatrixError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if maximum_bytes is not None and len(content) > maximum_bytes:
        raise GGUFCandidateMatrixError(f"file exceeds the allowed size: {path}")
    return content


def load_gguf_matrix(path: Path) -> Qwen4090CandidateMatrixV2:
    try:
        return Qwen4090CandidateMatrixV2.model_validate_json(
            _regular_file(path, maximum_bytes=MAX_MATRIX_BYTES)
        )
    except ValidationError as error:
        raise GGUFCandidateMatrixError(
            "GGUF candidate matrix failed its strict v2 schema"
        ) from error


def verify_inputs(
    matrix: Qwen4090CandidateMatrixV2,
    *,
    dataset_path: Path,
    legacy_matrix_path: Path,
) -> None:
    dataset_digest = "sha256:" + hashlib.sha256(_regular_file(dataset_path)).hexdigest()
    if dataset_digest != matrix.qualification_dataset_digest:
        raise GGUFCandidateMatrixError("qualification dataset digest drifted")

    legacy_content = _regular_file(legacy_matrix_path, maximum_bytes=MAX_MATRIX_BYTES)
    legacy_digest = "sha256:" + hashlib.sha256(legacy_content).hexdigest()
    if legacy_digest != matrix.legacy_baseline.matrix_digest:
        raise GGUFCandidateMatrixError("immutable v1 candidate matrix digest drifted")
    legacy = load_legacy_matrix(legacy_matrix_path)
    if legacy.schema_version != matrix.legacy_baseline.matrix_schema_version:
        raise GGUFCandidateMatrixError("legacy matrix schema does not match the baseline pointer")
    matches = tuple(
        candidate
        for candidate in legacy.candidates
        if candidate.candidate_id == matrix.legacy_baseline.candidate_id
    )
    if len(matches) != 1:
        raise GGUFCandidateMatrixError("legacy baseline candidate is not present exactly once")


def build_report(matrix: Qwen4090CandidateMatrixV2) -> dict[str, object]:
    assessments = assess_gguf_matrix(matrix)
    eligible = tuple(
        assessment.candidate_id
        for assessment in assessments
        if assessment.status is CandidateReleaseStatusV2.RELEASE_ELIGIBLE
    )
    return {
        "schema_version": "qwen4090_candidate_assessment/2.0.0",
        "candidate_matrix_digest": matrix.matrix_digest,
        "legacy_baseline": matrix.legacy_baseline.model_dump(mode="json"),
        "target_gpu_name": matrix.target_gpu_name,
        "qualification_dataset_version": matrix.qualification_dataset_version,
        "qualification_dataset_digest": matrix.qualification_dataset_digest,
        "release_status": "RELEASE_ELIGIBLE" if eligible else "NO_RELEASE_ELIGIBLE",
        "eligible_candidate_ids": eligible,
        "assessments": [assessment.model_dump(mode="json") for assessment in assessments],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--legacy-matrix", type=Path, default=DEFAULT_LEGACY_MATRIX)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--require-eligible", action="store_true")
    arguments = parser.parse_args()
    try:
        matrix = load_gguf_matrix(arguments.matrix)
        verify_inputs(
            matrix,
            dataset_path=arguments.dataset,
            legacy_matrix_path=arguments.legacy_matrix,
        )
        report = build_report(matrix)
    except (GGUFCandidateMatrixError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"release_status": "INVALID", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if arguments.require_eligible and report["release_status"] != "RELEASE_ELIGIBLE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
