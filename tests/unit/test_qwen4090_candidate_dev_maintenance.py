from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "infra/llm/run_qwen4090_candidate_dev_maintenance.sh"
CANDIDATE_ID = "qwen38-27b-csight-q4-k-m-llama-cpp"


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("LLM_MODEL_ID=synthetic\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(mode=0o700)
    evidence_root.chmod(0o700)
    completion_parent = tmp_path / "completion-parent"
    completion_parent.mkdir(mode=0o700)
    completion_parent.chmod(0o700)
    completion_state = completion_parent / "run-1"
    sentinel = ROOT / "infra/llm/qwen4090_candidate_dev_completion.sh"
    subprocess.run(
        [str(sentinel), "prepare", CANDIDATE_ID, str(completion_state)],
        check=True,
        capture_output=True,
        text=True,
    )

    capture = tmp_path / "captured.txt"
    maintenance = tmp_path / "maintenance.sh"
    maintenance.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nprintf \'%s\\n\' "$@" >"${CAPTURE_FILE}"\n',
        encoding="utf-8",
    )
    maintenance.chmod(0o700)
    completion = tmp_path / "completion.sh"
    completion.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    completion.chmod(0o700)
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "ALLOW_VLM_MAINTENANCE": "YES",
        "CSIGHT_QWEN4090_DEV_CANDIDATE_ID": CANDIDATE_ID,
        "CSIGHT_QWEN4090_DEV_RUNTIME_ENV": str(runtime_env),
        "CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT": str(evidence_root),
        "CSIGHT_QWEN4090_DEV_COMPLETION_STATE": str(completion_state),
        "CSIGHT_QWEN4090_DEV_COMPLETION_TIMEOUT_SECONDS": "600",
        "CSIGHT_QWEN4090_LOCAL_DEV_MAINTENANCE_SCRIPT": str(maintenance),
        "CSIGHT_QWEN4090_DEV_COMPLETION_SCRIPT": str(completion),
        "CAPTURE_FILE": str(capture),
    }
    return environment, capture, runtime_env


def test_candidate_dev_bridge_execs_argumentful_inner_maintenance(tmp_path: Path) -> None:
    environment, capture, runtime_env = _environment(tmp_path)

    subprocess.run(
        [str(BRIDGE)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    arguments = capture.read_text(encoding="utf-8").splitlines()
    assert arguments == [
        CANDIDATE_ID,
        str(runtime_env),
        environment["CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT"],
        "--",
        environment["CSIGHT_QWEN4090_DEV_COMPLETION_SCRIPT"],
        "wait",
        CANDIDATE_ID,
        environment["CSIGHT_QWEN4090_DEV_COMPLETION_STATE"],
        "600",
    ]


def test_candidate_dev_bridge_rejects_public_runtime_env(tmp_path: Path) -> None:
    environment, capture, runtime_env = _environment(tmp_path)
    del capture
    runtime_env.chmod(0o644)

    result = subprocess.run(
        [str(BRIDGE)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "mode 600" in result.stderr


def test_candidate_dev_bridge_rejects_consumed_or_mismatched_completion_state(
    tmp_path: Path,
) -> None:
    environment, capture, runtime_env = _environment(tmp_path)
    del capture, runtime_env
    request = Path(environment["CSIGHT_QWEN4090_DEV_COMPLETION_STATE"]) / "request.tsv"
    request.write_text(
        "schema_version=qwen4090_candidate_dev_completion_request/1.0.0\n"
        "candidate_id=qwen38-27b-csight-q5-k-s-llama-cpp\n",
        encoding="utf-8",
    )
    request.chmod(0o600)

    result = subprocess.run(
        [str(BRIDGE)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "differs" in result.stderr


def test_candidate_dev_bridge_is_no_argument_and_shell_valid() -> None:
    source = BRIDGE.read_text(encoding="utf-8")
    completion_source = (ROOT / "infra/llm/qwen4090_candidate_dev_completion.sh").read_text(
        encoding="utf-8"
    )
    subprocess.run(["bash", "-n", str(BRIDGE)], check=True)

    assert 'if [[ "$#" -ne 0' in source
    assert 'exec "${maintenance_script}"' in source
    assert '"${completion_script}" wait' in source
    assert "CSIGHT_QWEN4090_DEV_COMPLETION_STATE" in source
    assert "CSIGHT_QWEN4090_DEV_RUNTIME_ENV" in source
    assert "CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT" in source
    assert source.index("stat -c '%u:%a'") < source.index("stat -f '%u:%Lp'")
    assert completion_source.index("stat -c '%u:%a'") < completion_source.index("stat -f '%u:%Lp'")
    assert "rm " not in source
    assert stat.S_IMODE(BRIDGE.stat().st_mode) == 0o755
