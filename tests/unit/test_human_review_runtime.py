"""Human-review migration, queue envelope, worker, and composition contracts."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import SecretStr
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from app.adapters.messaging.celery import CeleryHumanReviewMessageQueue
from app.adapters.persistence.models import (
    HumanReviewDecisionBasisModel,
    HumanReviewTaskModel,
    PolicyCitationPackItemModel,
)
from app.bootstrap.settings import Settings
from app.interface.workers.celery_app import (
    HUMAN_REVIEW_REQUESTED_TASK_NAME,
    create_celery_app,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


class _CeleryRecorder:
    def __init__(self) -> None:
        self.call: dict[str, object] | None = None

    def send_task(self, name: str, **values: object) -> None:
        self.call = {"name": name, **values}


def test_human_review_queue_is_identifier_only_and_routes_to_dedicated_queue() -> None:
    recorder = _CeleryRecorder()
    queue = CeleryHumanReviewMessageQueue(recorder)  # type: ignore[arg-type]
    payload = {
        "event_id": "event-1",
        "tenant_id": "tenant-1",
        "case_id": "case-1",
        "policy_evaluation_run_id": "policy-1",
        "correlation_id": "corr-1",
    }
    assert (
        queue.publish(
            topic=HUMAN_REVIEW_REQUESTED_TASK_NAME,
            payload=payload,
            correlation_id="corr-1",
        )
        == "event-1"
    )
    assert recorder.call == {
        "name": HUMAN_REVIEW_REQUESTED_TASK_NAME,
        "args": [payload],
        "task_id": "event-1",
        "queue": "human-review",
        "headers": {"correlation_id": "corr-1"},
    }
    with pytest.raises(ValueError, match="exactly five IDs"):
        queue.publish(
            topic=HUMAN_REVIEW_REQUESTED_TASK_NAME,
            payload={**payload, "customer_text": "forbidden"},
            correlation_id="corr-1",
        )


def test_celery_routes_human_review_without_changing_existing_safety_limits() -> None:
    application = create_celery_app(
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            rabbitmq_url=SecretStr("amqp://user:password@rabbitmq:5672//"),
        )
    )
    assert application.conf.task_routes[HUMAN_REVIEW_REQUESTED_TASK_NAME] == {
        "queue": "human-review"
    }
    assert application.conf.task_acks_late is True
    assert application.conf.task_reject_on_worker_lost is True
    assert application.conf.worker_prefetch_multiplier == 1


def test_worker_can_only_call_task_creation_use_case() -> None:
    path = ROOT / "app/interface/workers/tasks.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    worker = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "create_human_review_task"
    )
    source = ast.unparse(worker)
    forbidden = (
        "HumanReviewDecisionModel",
        "HumanDecisionRequest",
        ".resolve(",
        "APPROVE_REFUND",
        "APPROVE_EXCHANGE",
        "REJECT_REQUEST",
    )
    assert not [value for value in forbidden if value in source]
    assert "build_create_review_task" in source


def test_revision_0011_is_linear_and_previous_migration_is_not_reauthored() -> None:
    migration = ROOT / "alembic/versions/20260827_0011_human_review.py"
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
        "revision": "20260827_0011_human_review",
        "down_revision": "20260827_0010_policy_engine",
    }
    source = migration.read_text(encoding="utf-8")
    for table in (
        "human_review_tasks",
        "human_review_packets",
        "human_review_actions",
        "human_review_assignments",
        "human_review_decisions",
        "human_review_decision_basis",
        "human_review_request_events",
    ):
        assert table in source


def test_review_projection_and_basis_metadata_enforce_integrity_links() -> None:
    task_table = cast(Table, HumanReviewTaskModel.__table__)
    task_check = next(
        item
        for item in task_table.constraints
        if isinstance(item, CheckConstraint)
        and item.name is not None
        and str(item.name).endswith("assignee_status_consistent")
    )
    task_sql = str(task_check.sqltext)
    assert "status = 'CLAIMED'" in task_sql
    assert "status <> 'CLAIMED'" in task_sql

    basis_table = cast(Table, HumanReviewDecisionBasisModel.__table__)
    basis_check = next(
        item
        for item in basis_table.constraints
        if isinstance(item, CheckConstraint)
        and item.name is not None
        and str(item.name).endswith("typed_reference_consistent")
    )
    basis_sql = str(basis_check.sqltext)
    assert "basis_type = 'POLICY_CITATION'" in basis_sql
    assert "policy_clause_row_id IS NOT NULL" in basis_sql
    assert "citation_item_id IS NOT NULL" in basis_sql

    pack_item_table = cast(Table, PolicyCitationPackItemModel.__table__)
    pack_unique = next(
        item
        for item in pack_item_table.constraints
        if isinstance(item, UniqueConstraint)
        and item.name is not None
        and str(item.name).endswith("tenant_id_clause")
    )
    assert tuple(column.name for column in pack_unique.columns) == (
        "tenant_id",
        "id",
        "policy_clause_row_id",
    )

    citation_clause_fk = next(
        item
        for item in basis_table.constraints
        if isinstance(item, ForeignKeyConstraint)
        and item.name is not None
        and str(item.name).endswith("citation_clause")
    )
    assert tuple(column.name for column in citation_clause_fk.columns) == (
        "tenant_id",
        "citation_item_id",
        "policy_clause_row_id",
    )
    assert tuple(element.target_fullname for element in citation_clause_fk.elements) == (
        "policy_citation_pack_items.tenant_id",
        "policy_citation_pack_items.id",
        "policy_citation_pack_items.policy_clause_row_id",
    )
