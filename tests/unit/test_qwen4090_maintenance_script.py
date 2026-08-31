"""Static safety contract for the single-GPU maintenance runner."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra/llm/run_qwen4090_maintenance_dev.sh"


def test_maintenance_runner_is_explicit_shadow_dev_with_exit_restoration() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert 'ALLOW_VLM_MAINTENANCE:-}" != "YES"' in content
    assert "trap restore_vlm EXIT" in content
    assert "stop_candidate" in content
    assert "VLM_RESTORED_HEALTHY" in content
    assert "CANDIDATE_FAILURE_LOG_WRITTEN" in content
    assert "logs --no-color --tail 400 qwen38" in content
    assert 'chmod 600 "${candidate_failure_log}"' in content
    assert "--pull=never" in content
    assert "--split dev" in content
    assert "--allow-sealed-test" not in content
    assert "--split test" not in content
    assert "LLM_API_KEY" not in content
