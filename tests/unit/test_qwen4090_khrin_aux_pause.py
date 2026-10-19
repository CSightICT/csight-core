"""Fail-safe contracts for temporarily pausing Khrin auxiliary containers."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "infra/llm/run_qwen4090_khrin_aux_pause.sh"
WATCHDOG = ROOT / "infra/llm/qwen4090_khrin_aux_restore_watchdog.sh"


def test_khrin_pause_scripts_are_valid_and_use_an_exact_allowlist() -> None:
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    subprocess.run(["bash", "-n", str(WATCHDOG)], check=True)
    assert stat.S_IMODE(WRAPPER.stat().st_mode) == 0o755
    assert stat.S_IMODE(WATCHDOG.stat().st_mode) == 0o755

    result = subprocess.run(
        ["bash", str(WRAPPER), "--print-allowlist"],
        cwd=ROOT,
        env={"PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        check=True,
    )
    names = result.stdout.splitlines()
    assert len(names) == 12
    assert len(names) == len(set(names))
    assert all(name.startswith("counsel-rag-") for name in names)
    assert all("*" not in name for name in names)


def test_khrin_pause_installs_restore_guards_before_the_first_stop() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    backend_probe_position = source.index("backend_probe_output=")
    watchdog_position = source.index('nohup setsid bash "${watchdog_script}" monitor')
    exit_trap_position = source.index("trap cleanup EXIT")
    hup_trap_position = source.index("trap 'exit 129' HUP")
    stop_position = source.index('docker stop --time 30 "${name}"')
    maintenance_position = source.index('setsid bash "${watchdog_script}" launch-maintenance')

    assert backend_probe_position < watchdog_position
    assert watchdog_position < exit_trap_position < hup_trap_position < stop_position
    assert stop_position < maintenance_position
    assert '--entrypoint /app/llama-imatrix "${tool_image}" --list-devices' in source
    assert 'grep -Fq "Available devices:"' in source
    assert "'^  CUDA[0-9]+:'" in source
    assert "{{.Id}}" in source
    assert "{{.Image}}" in source
    assert "{{.Config.Image}}" in source
    assert "only already-running containers may be paused" in source


def test_watchdog_never_claims_a_preexisting_unhealthy_container_is_healthy() -> None:
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "IDENTITY_MISMATCH_NOT_STARTED" in source
    assert "RESTORED_HEALTHY" in source
    assert "RESTORED_RUNNING_BASELINE_${expected_health^^}" in source
    assert "STILL_RUNNING_AUX_NOT_RESTORED" in source
    assert "kill -HUP" in source
