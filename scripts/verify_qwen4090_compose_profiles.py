"""Verify that every runnable RTX 4090 Shadow Compose profile matches the frozen matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.platform.qwen4090_release import (
    CandidateRole,
    Qwen4090Candidate,
    Qwen4090CandidateMatrix,
)
from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = ROOT / "infra/llm/candidates"
MAX_PROFILE_BYTES = 64 * 1024


class ComposeProfileError(RuntimeError):
    """A runnable profile drifted from its candidate matrix identity."""


def _regular_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ComposeProfileError(f"required regular profile is missing: {path}")
    content = path.read_bytes()
    if len(content) > MAX_PROFILE_BYTES:
        raise ComposeProfileError(f"profile exceeds the allowed size: {path}")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ComposeProfileError(f"profile is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ComposeProfileError(f"profile root must be a JSON object: {path}")
    return value


def _expected_command(candidate: Qwen4090Candidate) -> list[str]:
    return [
        candidate.artifact.artifact,
        "--revision",
        candidate.artifact.artifact_revision,
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--served-model-name",
        candidate.serving.served_model_name,
        "--language-model-only",
        "--max-model-len",
        str(candidate.serving.max_context_tokens),
        "--max-num-seqs",
        str(candidate.serving.max_num_sequences),
        "--gpu-memory-utilization",
        str(candidate.serving.gpu_memory_utilization),
        "--kv-cache-dtype",
        candidate.serving.kv_cache_dtype,
        "--enforce-eager",
        "--reasoning-parser",
        "qwen3",
        "--default-chat-template-kwargs",
        '{"enable_thinking":false,"preserve_thinking":false}',
    ]


def _candidate_profiles(matrix: Qwen4090CandidateMatrix) -> dict[str, Qwen4090Candidate]:
    runnable_roles = {CandidateRole.MODEL_CHALLENGER, CandidateRole.RUNTIME_CHALLENGER}
    return {
        candidate.candidate_id: candidate
        for candidate in matrix.candidates
        if candidate.role in runnable_roles
    }


def verify_profiles(
    matrix: Qwen4090CandidateMatrix,
    profile_dir: Path,
) -> tuple[dict[str, object], ...]:
    expected = _candidate_profiles(matrix)
    if profile_dir.is_symlink() or not profile_dir.is_dir():
        raise ComposeProfileError("candidate profile directory is missing or unsafe")
    observed_paths = {
        path.name.removesuffix(".compose.json"): path for path in profile_dir.glob("*.compose.json")
    }
    if set(observed_paths) != set(expected):
        raise ComposeProfileError("candidate profile set does not match runnable matrix candidates")

    reports: list[dict[str, object]] = []
    for candidate_id in sorted(expected):
        candidate = expected[candidate_id]
        profile = _regular_json(observed_paths[candidate_id])
        services = profile.get("services")
        if not isinstance(services, dict) or set(services) != {"qwen38"}:
            raise ComposeProfileError(f"{candidate_id}: exactly one qwen38 override is required")
        service = services["qwen38"]
        if not isinstance(service, dict) or set(service) != {"image", "labels", "command"}:
            raise ComposeProfileError(f"{candidate_id}: unexpected Compose service keys")
        expected_image = (
            f"{candidate.serving.runtime_image}@{candidate.serving.runtime_image_digest}"
        )
        if service.get("image") != expected_image:
            raise ComposeProfileError(f"{candidate_id}: runtime image identity drifted")
        expected_labels = {
            "org.csight.qwen4090.candidate-id": candidate_id,
            "org.csight.qwen4090.execution-mode": "SHADOW",
        }
        if service.get("labels") != expected_labels:
            raise ComposeProfileError(f"{candidate_id}: Shadow labels drifted")
        if service.get("command") != _expected_command(candidate):
            raise ComposeProfileError(f"{candidate_id}: artifact or serving command drifted")
        reports.append(
            {
                "candidate_id": candidate_id,
                "artifact": candidate.artifact.artifact,
                "artifact_revision": candidate.artifact.artifact_revision,
                "runtime_image": expected_image,
                "served_model_name": candidate.serving.served_model_name,
                "execution_mode": "SHADOW",
                "status": "PROFILE_VERIFIED",
            }
        )
    return tuple(reports)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    arguments = parser.parse_args()
    try:
        reports = verify_profiles(load_matrix(arguments.matrix), arguments.profile_dir)
    except (ComposeProfileError, OSError, ValueError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "schema_version": "qwen4090_compose_profiles/1.0.0",
                "status": "PASS",
                "profiles": reports,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
