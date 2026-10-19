from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "infra/llm/run_gx10_model_engine.sh"
REMOTE = ROOT / "infra/llm/gx10_remote_model_engine.sh"
BUILD = ROOT / "infra/llm/build_llama_cpp_gx10_image.sh"
DOCKERFILE = ROOT / "infra/llm/llama.cpp-gx10/Dockerfile"
COMPOSE = ROOT / "infra/llm/compose.llama-cpp-gx10.yml"


def test_gx10_scripts_are_shell_valid_and_executable() -> None:
    for script in (CONTROLLER, REMOTE, BUILD):
        subprocess.run(["bash", "-n", str(script)], check=True)
        assert stat.S_IMODE(script.stat().st_mode) == 0o755


def test_gx10_build_is_arm64_sm121_and_does_not_change_4090_contract() -> None:
    gx10_build = BUILD.read_text(encoding="utf-8")
    gx10_dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    existing_build = (ROOT / "infra/llm/build_llama_cpp_image.sh").read_text(encoding="utf-8")
    existing_dockerfile = (ROOT / "infra/llm/llama.cpp/Dockerfile").read_text(encoding="utf-8")

    assert "--platform=linux/arm64" in gx10_build
    assert '"$(uname -m)" != "aarch64"' in gx10_build
    assert "-DCMAKE_CUDA_ARCHITECTURES=121" in gx10_dockerfile
    assert "-DGGML_CPU_ALL_VARIANTS=OFF" in gx10_dockerfile
    assert "GX10_LLAMA_CPP_DOCKERFILE_DIR" in gx10_build
    assert "--platform=linux/amd64" in existing_build
    assert "-DCMAKE_CUDA_ARCHITECTURES=89" in existing_dockerfile
    assert "-DGGML_CPU_ALL_VARIANTS=ON" in existing_dockerfile


def test_gx10_runtime_is_canary_only_and_primary_forbidden() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "nvidia.com/gpu=all" in compose
    assert "LLAMA_CPP_RUN_UID" in compose
    assert "LLAMA_CPP_RUN_GID" in compose
    assert "LLAMA_CPP_REASONING:-off" in compose
    assert "org.csight.execution-scope: GX10_CANARY_DEV_ONLY" in compose
    assert 'org.csight.primary-allowed: "false"' in compose
    assert 'org.csight.core-routing: "false"' in compose
    assert 'org.csight.automatic-fallback: "false"' in compose
    assert 'org.csight.primary-allowed="false"' in dockerfile


def test_controller_exposes_all_phases_and_forbids_password_authentication() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    for phase in ("status", "prepare", "serve", "canary", "evaluate", "report", "stop"):
        assert phase in source
    assert "PasswordAuthentication=no" in source
    assert "KbdInteractiveAuthentication=no" in source
    assert "BatchMode=yes" in source
    assert "ALLOW_GX10_MUTATION" in source
    assert "sshpass" not in source.lower()
    assert "read -s" not in source.lower()
    assert "PasswordAuthentication=yes" not in source
    assert "GX10_BENCHMARK_SCRIPT" in source


def test_controller_rejects_mutation_without_gate() -> None:
    result = subprocess.run(
        [str(CONTROLLER), "prepare", "20260902T010000"],
        env={"PATH": os.environ.get("PATH", "")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "requires ALLOW_GX10_MUTATION=YES" in result.stderr


def test_remote_runner_has_append_only_evidence_and_failure_cleanup() -> None:
    source = REMOTE.read_text(encoding="utf-8")

    assert "RUN_EVIDENCE_ALREADY_EXISTS" in source
    assert "PHASE_EVIDENCE_ALREADY_EXISTS" in source
    assert "cleanup_failed_start" in source
    assert "serve-container.log" in source
    assert "GX10_SERVE_START_FAILED" in source
    assert "down --remove-orphans" in source
    assert "expected_model_bytes=18679614080" in source
    assert 'sha256sum "${expected_model}"' in source
    assert "GX10_MODEL_SHA256_MISMATCH" in source
    assert "GX10_IMAGE_ID_MISMATCH" in source
    assert "GX10_RUNTIME_OWNER_MISMATCH" in source
    assert "GX10_BENCHMARK_CONTRACT_INVALID" in source
    assert "GX10_BENCHMARK_FAILED" in source
    assert "peak_unified_memory_bytes" in source
    assert (
        'expected_model_sha="d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219"'
        in source
    )
    assert '"schema": "csight_gx10_run_summary/1.0.0"' in source
