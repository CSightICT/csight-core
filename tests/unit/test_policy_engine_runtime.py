"""Queue, worker payload, migration, and architecture contracts for Sprint 5A."""

import ast
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.adapters.messaging import CeleryPolicyEvaluationMessageQueue
from app.interface.workers.celery_app import (
    POLICY_EVALUATION_REQUESTED_TASK_NAME,
    create_celery_app,
)

pytestmark = pytest.mark.unit


class _Celery:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_task(self, name: str, **values: Any) -> None:
        self.sent.append({"name": name, **values})


def test_policy_queue_is_identifier_only_and_routed() -> None:
    celery = _Celery()
    queue = CeleryPolicyEvaluationMessageQueue(celery)  # pyright: ignore[reportArgumentType]
    payload = {
        "event_id": "event-1",
        "tenant_id": "tenant-1",
        "case_id": "case-1",
        "policy_evaluation_run_id": "run-1",
        "correlation_id": "corr-1",
    }
    assert (
        queue.publish(
            topic=POLICY_EVALUATION_REQUESTED_TASK_NAME,
            payload=payload,
            correlation_id="corr-1",
        )
        == "event-1"
    )
    assert celery.sent[0]["queue"] == "policy-evaluation"
    assert celery.sent[0]["args"] == [payload]
    with pytest.raises(ValueError):
        queue.publish(
            topic=POLICY_EVALUATION_REQUESTED_TASK_NAME,
            payload={**payload, "customer_message": "private"},
            correlation_id="corr-1",
        )
    configured = create_celery_app()
    assert configured.conf.task_routes[POLICY_EVALUATION_REQUESTED_TASK_NAME] == {
        "queue": "policy-evaluation"
    }


def test_migration_0010_is_single_head_and_contains_all_policy_tables() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", str(Path("alembic")))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20260827_0010_policy_engine")
    assert scripts.get_heads() == ["20260827_0015_vision_image_assessment"]
    assert revision is not None and revision.down_revision == "20260827_0009"
    source = Path("alembic/versions/20260827_0010_policy_engine.py").read_text()
    for table in (
        "policy_rule_sets",
        "policy_rule_set_activations",
        "policy_rules",
        "policy_rule_source_clauses",
        "policy_evaluation_runs",
        "policy_evaluation_input_snapshots",
        "policy_rule_evaluation_results",
        "policy_condition_evaluation_results",
        "policy_evaluation_effects",
        "policy_evaluation_outbox_events",
    ):
        assert f'"{table}"' in source


def test_policy_engine_has_no_dynamic_execution_or_framework_imports() -> None:
    platform = Path("app/platform/policy_engine/__init__.py")
    tree = ast.parse(platform.read_text(encoding="utf-8"))
    imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not imports & {"fastapi", "sqlalchemy", "celery", "httpx", "openai"}
    assert not calls & {"eval", "exec", "compile"}

    worker = Path("app/interface/workers/tasks.py").read_text(encoding="utf-8")
    router = Path("app/interface/http/routers/policy_evaluations.py").read_text(encoding="utf-8")
    assert "evaluate_rule" not in worker
    assert "PolicyCondition" not in router
