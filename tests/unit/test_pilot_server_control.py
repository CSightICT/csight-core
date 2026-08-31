"""Safety contract for the separate pilot server controller."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts/csight_pilot_control.sh"


def test_pilot_controller_preflights_before_no_build_start_and_preserves_volumes() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert source.index('run_preflight "${uv_bin}"') < source.index("up --detach --wait --no-build")
    assert 'compose_command "${docker_bin}" stop' in source
    assert "infra/compose.core.yml" in source
    assert "infra/compose.rls.yml" in source
    assert "infra/evidence/compose.evidence-security.yml" in source
    assert "infra/pilot/compose.pilot.yml" in source
    assert "--profile pilot-maintenance" in source
    for forbidden in (
        "docker system prune",
        "volume rm",
        "down --volumes",
        "up --build",
        "alembic upgrade",
        "qualify_restore_drill",
    ):
        assert forbidden not in source
    assert CONTROLLER.stat().st_mode & 0o100


def test_failed_preflight_never_calls_docker_start(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        f"#!/bin/sh\nprintf 'uv %s\\n' \"$*\" >> '{log}'\nexit 2\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        f"#!/bin/sh\nprintf 'docker %s\\n' \"$*\" >> '{log}'\nexit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env_file = tmp_path / ".env.pilot"
    env_file.write_text("ENVIRONMENT=pilot\n", encoding="utf-8")
    env_file.chmod(0o600)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["CSIGHT_PILOT_ENV_FILE"] = os.fspath(env_file)

    completed = subprocess.run(
        [os.fspath(CONTROLLER), "start"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 2
    calls = log.read_text(encoding="utf-8")
    assert "uv run python" in calls
    assert "docker compose" not in calls
