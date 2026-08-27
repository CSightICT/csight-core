"""Sprint 5C metadata, migration, broker, and worker boundary contracts."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from celery import Celery
from pydantic import SecretStr
from sqlalchemy import CheckConstraint, Table, UniqueConstraint

from app.adapters.messaging import (
    CeleryCaseResolutionMessageQueue,
    CeleryExternalActionSimulationMessageQueue,
)
from app.adapters.persistence.models import PERSISTENCE_MODELS, ExternalActionIntentModel
from app.application.case_resolution import ExecuteExternalActionSimulation
from app.bootstrap.settings import Settings
from app.interface.workers.celery_app import (
    CASE_RESOLUTION_REQUESTED_TASK_NAME,
    EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME,
    create_celery_app,
)
from app.interface.workers.tasks import execute_external_action_simulation_task
from app.platform.async_reliability import ExecutionLeaseActiveError
from app.platform.case_resolution import (
    ExternalActionIntent,
    ExternalActionType,
    SimulationClaim,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


class _CeleryRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_task(self, name: str, **values: object) -> None:
        self.calls.append({"name": name, **values})


@pytest.mark.parametrize(
    ("queue", "topic", "payload", "queue_name"),
    [
        (
            "resolution",
            CASE_RESOLUTION_REQUESTED_TASK_NAME,
            {
                "event_id": "event-1",
                "tenant_id": "tenant-1",
                "case_id": "case-1",
                "resolution_id": "resolution-1",
                "correlation_id": "corr-1",
            },
            "case-resolution",
        ),
        (
            "simulation",
            EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME,
            {
                "event_id": "event-2",
                "tenant_id": "tenant-1",
                "case_id": "case-1",
                "external_action_intent_id": "intent-1",
                "correlation_id": "corr-1",
            },
            "external-action-simulation",
        ),
    ],
)
def test_5c_queues_publish_only_five_opaque_identifiers(
    queue: str,
    topic: str,
    payload: dict[str, object],
    queue_name: str,
) -> None:
    recorder = _CeleryRecorder()
    publisher = (
        CeleryCaseResolutionMessageQueue(cast(Celery, recorder))
        if queue == "resolution"
        else CeleryExternalActionSimulationMessageQueue(cast(Celery, recorder))
    )
    assert (
        publisher.publish(topic=topic, payload=payload, correlation_id="corr-1")
        == payload["event_id"]
    )
    assert recorder.calls[0]["queue"] == queue_name
    with pytest.raises(ValueError, match="exactly five IDs"):
        publisher.publish(
            topic=topic,
            payload={**payload, "customer_message": "forbidden"},
            correlation_id="corr-1",
        )


def test_5c_celery_routes_keep_late_ack_and_worker_loss_rejection() -> None:
    application = create_celery_app(
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            rabbitmq_url=SecretStr("amqp://user:password@rabbitmq:5672//"),
        )
    )
    assert application.conf.task_routes[CASE_RESOLUTION_REQUESTED_TASK_NAME] == {
        "queue": "case-resolution"
    }
    assert application.conf.task_routes[EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME] == {
        "queue": "external-action-simulation"
    }
    assert application.conf.task_acks_late is True
    assert application.conf.task_reject_on_worker_lost is True


def test_5c_models_are_registered_and_intent_is_typed_dry_run_only() -> None:
    expected = {
        "case_resolutions",
        "case_resolution_events",
        "case_resolution_request_events",
        "external_action_intents",
        "external_action_simulation_request_events",
        "external_action_simulation_attempts",
        "external_action_simulation_results",
    }
    assert expected.issubset({model.__tablename__ for model in PERSISTENCE_MODELS})
    table = cast(Table, ExternalActionIntentModel.__table__)
    check_sql = {
        str(item.name): str(item.sqltext)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    }
    assert "mode = 'DRY_RUN'" in check_sql["ck_external_action_intents_dry_run_only"]
    assert (
        "action_type = 'REFUND'" in check_sql["ck_external_action_intents_typed_input_consistent"]
    )
    unique_names = {
        str(item.name) for item in table.constraints if isinstance(item, UniqueConstraint)
    }
    assert "uq_external_action_intents_resolution" in unique_names


def test_revision_0013_is_linear_and_workers_do_not_expose_live_execution() -> None:
    migration = ROOT / "alembic/versions/20260827_0013_case_resolution_external_action.py"
    namespace: dict[str, Any] = {}
    tree = ast.parse(migration.read_text(encoding="utf-8"), filename=str(migration))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
            and node.value is not None
        ):
            namespace[node.target.id] = ast.literal_eval(node.value)
    assert namespace == {
        "revision": "20260827_0013_case_resolution_external_action",
        "down_revision": "20260827_0012_async_reliability",
    }
    worker_source = (ROOT / "app/interface/workers/tasks.py").read_text(encoding="utf-8")
    assert "execute_external_action_simulation_task" in worker_source
    assert "LIVE_EXTERNAL_ACTION" not in worker_source


def test_simulation_duplicate_at_celery_retry_limit_is_fenced_not_unbounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retry_at = datetime.now(UTC) + timedelta(minutes=5)
    service = MagicMock()
    service.execute.side_effect = ExecutionLeaseActiveError(retry_at=retry_at)
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        celery_task_max_retries=1,
    )

    def build_service(_settings: Settings) -> Any:
        return service

    monkeypatch.setattr(
        "app.interface.workers.tasks.build_execute_external_action_simulation",
        build_service,
    )
    monkeypatch.setattr("app.interface.workers.tasks.get_settings", lambda: settings)
    payload = {
        "event_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "case_id": str(uuid4()),
        "external_action_intent_id": str(uuid4()),
        "correlation_id": "corr-1",
    }

    eager_result = cast(Any, execute_external_action_simulation_task).apply(
        args=[payload],
        retries=3,
        throw=True,
    )

    assert eager_result.result["disposition"] == "FENCED_ACTIVE_LEASE"
    assert eager_result.result["retry_at"] == retry_at.isoformat()
    service.record_failure.assert_not_called()


def test_simulation_retry_exhaustion_records_only_its_acquired_lease_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = str(uuid4())
    repository = MagicMock()
    repository.prepare_simulation.return_value = SimulationClaim(
        event_id=str(uuid4()),
        tenant_id=str(uuid4()),
        case_id=str(uuid4()),
        resolution_id=str(uuid4()),
        intent=ExternalActionIntent(
            id=str(uuid4()),
            tenant_id=str(uuid4()),
            case_id=str(uuid4()),
            resolution_id=str(uuid4()),
            human_decision_id=str(uuid4()),
            action_type=ExternalActionType.REPAIR,
            order_ref="order-1",
            product_ref="product-1",
            quantity=1,
            content_hash="a" * 64,
            created_at=datetime.now(UTC),
        ),
        attempt_id=str(uuid4()),
        execution_token=token,
        correlation_id="corr-1",
    )
    adapter = MagicMock()
    adapter.simulate.side_effect = RuntimeError("transient adapter failure")
    service = ExecuteExternalActionSimulation(repository, adapter)
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        celery_task_max_retries=1,
    )

    def build_service(_settings: Settings) -> ExecuteExternalActionSimulation:
        return service

    monkeypatch.setattr(
        "app.interface.workers.tasks.build_execute_external_action_simulation",
        build_service,
    )
    monkeypatch.setattr("app.interface.workers.tasks.get_settings", lambda: settings)
    claim = repository.prepare_simulation.return_value
    payload = {
        "event_id": claim.event_id,
        "tenant_id": claim.tenant_id,
        "case_id": claim.case_id,
        "external_action_intent_id": claim.intent.id,
        "correlation_id": claim.correlation_id,
    }

    eager_result = cast(Any, execute_external_action_simulation_task).apply(
        args=[payload],
        retries=1,
        throw=True,
    )

    assert eager_result.result["disposition"] == "FAILED"
    repository.record_simulation_failure.assert_called_once_with(
        event_id=claim.event_id,
        code="EXTERNAL_ACTION_SIMULATION_WORKER_RETRIES_EXHAUSTED",
        message="Action simulation worker exhausted bounded infrastructure retries.",
        expected_execution_token=token,
    )
