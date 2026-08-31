"""Validate and assess the frozen RTX 4090 Qwen candidate matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.platform.qwen4090_release import (
    CandidateReleaseStatus,
    Qwen4090CandidateMatrix,
    assess_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "evaluation/llm/qwen4090_candidate_matrix_v1.json"
DEFAULT_DATASET = ROOT / "evaluation/llm_extraction_v2/gold.jsonl"
MAX_MATRIX_BYTES = 1024 * 1024


class CandidateMatrixError(RuntimeError):
    """The release evidence is malformed, drifted, or not release eligible."""


def _regular_file(path: Path, *, maximum_bytes: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CandidateMatrixError(f"required regular file is missing: {path}")
    content = path.read_bytes()
    if maximum_bytes is not None and len(content) > maximum_bytes:
        raise CandidateMatrixError(f"file exceeds the allowed size: {path}")
    return content


def load_matrix(path: Path) -> Qwen4090CandidateMatrix:
    try:
        return Qwen4090CandidateMatrix.model_validate_json(
            _regular_file(path, maximum_bytes=MAX_MATRIX_BYTES)
        )
    except ValidationError as error:
        raise CandidateMatrixError("candidate matrix failed its strict schema") from error


def verify_dataset(matrix: Qwen4090CandidateMatrix, dataset_path: Path) -> None:
    observed = "sha256:" + hashlib.sha256(_regular_file(dataset_path)).hexdigest()
    if observed != matrix.qualification_dataset_digest:
        raise CandidateMatrixError("qualification dataset digest drifted")


def build_report(matrix: Qwen4090CandidateMatrix) -> dict[str, object]:
    assessments = assess_matrix(matrix)
    eligible = tuple(
        item.candidate_id
        for item in assessments
        if item.status is CandidateReleaseStatus.RELEASE_ELIGIBLE
    )
    return {
        "schema_version": "qwen4090_candidate_assessment/1.0.0",
        "target_gpu_name": matrix.target_gpu_name,
        "qualification_dataset_version": matrix.qualification_dataset_version,
        "qualification_dataset_digest": matrix.qualification_dataset_digest,
        "release_status": "RELEASE_ELIGIBLE" if eligible else "NO_RELEASE_ELIGIBLE",
        "eligible_candidate_ids": eligible,
        "assessments": [item.model_dump(mode="json") for item in assessments],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--require-eligible", action="store_true")
    arguments = parser.parse_args()

    try:
        matrix = load_matrix(arguments.matrix)
        verify_dataset(matrix, arguments.dataset)
        report = build_report(matrix)
    except (CandidateMatrixError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"release_status": "INVALID", "error": str(error)}, sort_keys=True))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if arguments.require_eligible and report["release_status"] != "RELEASE_ELIGIBLE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
