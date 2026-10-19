"""Offline opt-in profile contracts; never contacts a model service."""

from pathlib import Path

import pytest
from pydantic import AnyHttpUrl

from app.bootstrap.settings import Settings
from app.bootstrap.sprint2 import _v2_prompt  # pyright: ignore[reportPrivateUsage]
from app.bootstrap.sprint4c3a import _grounding_prompt  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit


def test_internal_feedback_pins_separate_prompt_versions() -> None:
    settings = Settings(
        shadow_human_feedback_enabled=True,
        llm_provider="llama_cpp",
        llm_base_url=AnyHttpUrl("http://127.0.0.1:18004"),
    )
    assert _v2_prompt(settings).version == "2.0.0-local.8"
    assert _grounding_prompt(settings).version == "1.1.0-local.2"


def test_feedback_profile_uses_ssh_key_only_loopback_and_separate_overlay() -> None:
    script = Path("scripts/csight_internal_feedback.sh").read_text()
    for value in (
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "StrictHostKeyChecking=yes",
        "127.0.0.1:18004:127.0.0.1:18003",
        "ExitOnForwardFailure=yes",
    ):
        assert value in script
    overlay = Path("infra/compose.internal-feedback.yml").read_text()
    assert 'SHADOW_HUMAN_FEEDBACK_ENABLED: "true"' in overlay
    assert "LLM_PROVIDER: llama_cpp" in overlay
    assert "VISION_PROVIDER: remote" in overlay
    assert "shadow_human_feedback" not in Path("infra/pilot/compose.pilot.yml").read_text().lower()
