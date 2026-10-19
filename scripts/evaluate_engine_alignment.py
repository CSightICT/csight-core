"""Offline diagnostic replay and synthetic contract evaluation. No providers or DB calls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.domains.product_defect_cs.evidence_alignment import (
    AlignmentInput,
    AlignmentStatus,
    align_evidence,
    canonical_digest,
)
from app.platform.analysis.errors import LLMSourceQuoteMismatchError
from scripts.engine_alignment_fixtures import ContractCase, make_input

MAX_INPUT_BYTES = 2 * 1024 * 1024
DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1] / "evaluation/engine_alignment_v1/dev_contract.jsonl"
)


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("INPUT_TOO_LARGE")
    return data


def evaluate_dataset(path: Path) -> dict[str, Any]:
    data = read_bounded(path)
    cases = [ContractCase.model_validate_json(line) for line in data.splitlines() if line.strip()]
    if not cases or len(cases) > 500 or len({case.id for case in cases}) != len(cases):
        raise ValueError("INVALID_CONTRACT_DATASET")
    observations: list[dict[str, Any]] = []
    for case in cases:
        if len(case.expected) != len(case.claims):
            raise ValueError("EXPECTED_CLAIM_COUNT_MISMATCH")
        value = make_input(case)
        report = align_evidence(value)
        statuses = tuple(c.status for c in report.claims)
        reasons = {reason for claim in report.claims for reason in claim.reasons}
        exact = statuses == case.expected and set(case.required_reasons) <= reasons
        replay = report == align_evidence(value)
        observations.append(
            {
                "id": case.id,
                "contract_match": exact,
                "replay_match": replay,
                "claim_count": len(report.claims),
                "type_candidate_count": sum(
                    c.status is AlignmentStatus.TYPE_CANDIDATE for c in report.claims
                ),
                "unresolved_count": sum(
                    c.status is AlignmentStatus.UNRESOLVED for c in report.claims
                ),
                "report_sha256": canonical_digest(report),
            }
        )
    passed = sum(o["contract_match"] and o["replay_match"] for o in observations)
    return {
        "schema_version": "engine_alignment_contract_evaluation/1.0.0",
        "status": "PASS" if passed == len(cases) else "FAIL",
        "dataset_sha256": hashlib.sha256(data).hexdigest(),
        "evaluation_scope": "SYNTHETIC_CANONICAL_CONTRACT_ONLY",
        "cases": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "observations": observations,
        "model_quality": "NOT_RUN",
        "combined_model_gain": "NOT_RUN",
        "external_calls": 0,
        "business_side_effects": 0,
    }


def write_new_report(directory: Path, payload: dict[str, Any]) -> str:
    # Existing directories (including symlinks) are rejected; previous runs are never replaced.
    directory.mkdir(mode=0o700)
    data = (
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()
    fd = os.open(directory / "result.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("evaluate", "replay"))
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="New directory; parent must exist"
    )
    args = parser.parse_args()
    try:
        if args.mode == "evaluate":
            payload = evaluate_dataset(args.input or DEFAULT_DATASET)
        else:
            if args.input is None:
                raise ValueError("REPLAY_INPUT_REQUIRED")
            value = AlignmentInput.model_validate_json(read_bounded(args.input))
            report = align_evidence(value)
            payload = report.model_dump(mode="json")
        digest = write_new_report(args.output_dir, payload)
    except (ValueError, ValidationError, LLMSourceQuoteMismatchError, OSError):
        # Pydantic/OS diagnostics can contain customer values, paths or quotes. Do not print them.
        print(json.dumps({"status": "FAIL", "error": "ALIGNMENT_INPUT_OR_OUTPUT_REJECTED"}))
        return 2
    status = payload.get("status", "PASS")
    print(
        json.dumps(
            {
                "status": status,
                "phase": args.mode,
                "report_sha256": digest,
                "cases": payload.get("cases"),
                "passed": payload.get("passed"),
                "model_quality": "NOT_RUN",
                "external_calls": 0,
                "business_side_effects": 0,
            },
            separators=(",", ":"),
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
