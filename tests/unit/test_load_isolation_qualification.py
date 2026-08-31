"""Static safety and routing contracts for load/isolation qualification."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_queue_qualification_stack_is_internal_digest_pinned_and_has_no_ports() -> None:
    compose = yaml.safe_load(
        (ROOT / "infra/load/compose.queue-isolation-qualification.yml").read_text(encoding="utf-8")
    )
    assert compose["networks"]["qualification"]["internal"] is True
    assert "@sha256:" in compose["services"]["rabbitmq"]["image"]
    assert all("ports" not in service for service in compose["services"].values())


def test_queue_concurrency_matches_pilot_contract() -> None:
    compose = yaml.safe_load(
        (ROOT / "infra/load/compose.queue-isolation-qualification.yml").read_text(encoding="utf-8")
    )
    model_command = compose["services"]["model-worker"]["command"]
    decision_command = compose["services"]["decision-worker"]["command"]
    assert "--concurrency=1" in model_command
    assert "--queues=model-qualification" in model_command
    assert "--concurrency=2" in decision_command
    assert "--queues=decision-qualification" in decision_command


def test_qualification_tasks_are_fixed_synthetic_contracts() -> None:
    source = (ROOT / "scripts/queue_isolation_tasks.py").read_text(encoding="utf-8")
    assert "MODEL_DURATION_SECONDS = 120" in source
    assert "DECISION_COUNT = 20" in source
    assert "DATABASE_URL" not in source
    assert "refund" not in source.casefold()
