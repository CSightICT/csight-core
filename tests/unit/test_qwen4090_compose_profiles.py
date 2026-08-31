"""Matrix-locked RTX 4090 Shadow Compose profile tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.verify_qwen4090_candidates import DEFAULT_MATRIX, load_matrix
from scripts.verify_qwen4090_compose_profiles import (
    DEFAULT_PROFILE_DIR,
    ComposeProfileError,
    verify_profiles,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "infra/llm/serve_qwen_candidate.sh"
EXAMPLE_ENV = ROOT / "infra/llm/.env.llm.example"


def test_all_runnable_shadow_profiles_match_frozen_matrix() -> None:
    reports = verify_profiles(load_matrix(DEFAULT_MATRIX), DEFAULT_PROFILE_DIR)

    assert {report["candidate_id"] for report in reports} == {
        "qwen38-27b-awq-int4-community-vllm028",
        "qwen3-8b-fp8-official-vllm026",
    }
    assert all(report["execution_mode"] == "SHADOW" for report in reports)
    assert all(report["status"] == "PROFILE_VERIFIED" for report in reports)


def test_profile_runtime_or_command_drift_is_rejected(tmp_path: Path) -> None:
    profile_dir = tmp_path / "candidates"
    shutil.copytree(DEFAULT_PROFILE_DIR, profile_dir)
    target = profile_dir / "qwen3-8b-fp8-official-vllm026.compose.json"
    profile = json.loads(target.read_text(encoding="utf-8"))
    profile["services"]["qwen38"]["command"][2] = "0" * 40
    target.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(ComposeProfileError, match="command drifted"):
        verify_profiles(load_matrix(DEFAULT_MATRIX), profile_dir)


def test_missing_or_extra_candidate_profile_is_rejected(tmp_path: Path) -> None:
    profile_dir = tmp_path / "candidates"
    shutil.copytree(DEFAULT_PROFILE_DIR, profile_dir)
    (profile_dir / "qwen3-8b-fp8-official-vllm026.compose.json").unlink()

    with pytest.raises(ComposeProfileError, match="profile set"):
        verify_profiles(load_matrix(DEFAULT_MATRIX), profile_dir)


@pytest.mark.parametrize(
    ("candidate_id", "expected_model"),
    [
        (
            "qwen38-27b-awq-int4-community-vllm028",
            "csight-qwen3.8-27b-vllm028-shadow",
        ),
        ("qwen3-8b-fp8-official-vllm026", "csight-qwen3-8b-fp8-shadow"),
    ],
)
def test_candidate_launcher_dry_run_is_allowlisted_and_secret_free(
    candidate_id: str,
    expected_model: str,
) -> None:
    environment = os.environ.copy()
    environment["DRY_RUN"] = "1"

    completed = subprocess.run(
        [str(LAUNCHER), candidate_id, str(EXAMPLE_ENV)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert f"candidate={candidate_id}" in completed.stdout
    assert f"model={expected_model}" in completed.stdout
    assert "replace-with-a-long-random-secret" not in completed.stdout + completed.stderr


def test_candidate_launcher_rejects_non_matrix_profile() -> None:
    completed = subprocess.run(
        [str(LAUNCHER), "unapproved-model", str(EXAMPLE_ENV)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 2
    assert "not an allowlisted runnable Shadow profile" in completed.stderr
