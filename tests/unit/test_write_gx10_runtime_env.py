from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/write_gx10_runtime_env.py"


def test_runtime_env_is_fresh_private_and_contains_no_primary_identity(tmp_path: Path) -> None:
    parent = tmp_path / "runtime"
    parent.mkdir(mode=0o700)
    gguf_root = tmp_path / "models"
    gguf_root.mkdir(mode=0o700)
    output = parent / "gx10-q5.env"
    subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--path",
            str(output),
            "--image",
            "csight/llama.cpp:test",
            "--image-id",
            f"sha256:{'a' * 64}",
            "--gguf-root",
            str(gguf_root),
            "--gguf-filename",
            "model.gguf",
            "--model-id",
            "synthetic-model",
            "--bind-address",
            "100.64.0.1",
        ],
        check=True,
    )

    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert output.stat().st_mode & 0o777 == 0o600
    assert len(values["LLM_API_KEY"]) == 64
    assert values["LLAMA_CPP_CONTEXT_SIZE"] == "4096"
    assert values["LLAMA_CPP_CONTEXT_PER_SLOT"] == "4096"
    assert values["LLAMA_CPP_PARALLEL"] == "1"
    assert values["GX10_BENCHMARK_REQUESTS"] == "5"
    assert values["GX10_BENCHMARK_WARMUP"] == "1"
    assert values["LLAMA_CPP_REASONING"] == "off"
    assert not any("PRIMARY" in key or "ROUTE" in key for key in values)


def test_runtime_env_multiplies_context_by_parallel_slots(tmp_path: Path) -> None:
    parent = tmp_path / "runtime"
    parent.mkdir(mode=0o700)
    gguf_root = tmp_path / "models"
    gguf_root.mkdir(mode=0o700)
    output = parent / "gx10-q5-c4.env"
    subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--path",
            str(output),
            "--image",
            "csight/llama.cpp:test",
            "--image-id",
            f"sha256:{'a' * 64}",
            "--gguf-root",
            str(gguf_root),
            "--gguf-filename",
            "model.gguf",
            "--model-id",
            "synthetic-model",
            "--bind-address",
            "100.64.0.1",
            "--context-per-slot",
            "32768",
            "--parallel",
            "4",
            "--benchmark-requests",
            "8",
        ],
        check=True,
    )

    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["LLAMA_CPP_CONTEXT_SIZE"] == "131072"
    assert values["LLAMA_CPP_CONTEXT_PER_SLOT"] == "32768"
    assert values["LLAMA_CPP_PARALLEL"] == "4"
    assert values["GX10_BENCHMARK_REQUESTS"] == "8"
