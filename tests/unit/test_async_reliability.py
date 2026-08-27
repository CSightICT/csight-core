"""Focused contracts for the 0012 fenced async reliability baseline."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Integer, String, Uuid, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.adapters.persistence.models import (
    GroundedExplanationOutboxEventModel,
    GroundedExplanationRunModel,
    HumanReviewRequestEventModel,
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunModel,
)
from app.adapters.persistence.reliable_outbox import (
    ReliableOutboxSpec,
    ReliableSQLAlchemyOutboxDispatcher,
    TerminalRunFailure,
    exponential_retry_delay,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class _Base(DeclarativeBase):
    pass


class _Run(_Base):
    __tablename__ = "test_async_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    execution_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class _Outbox(_Base):
    __tablename__ = "test_async_outbox"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumer_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumer_last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class _Queue:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        fail: bool = False,
        consume_during_publish: bool = False,
    ) -> None:
        self._factory = factory
        self._fail = fail
        self._consume_during_publish = consume_during_publish
        self.calls: list[dict[str, object]] = []
        self.observed_statuses: list[str] = []

    def publish(
        self,
        *,
        topic: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> str:
        event_id = UUID(str(payload["event_id"]))
        with self._factory.begin() as session:
            event = session.get(_Outbox, event_id)
            assert event is not None
            self.observed_statuses.append(event.status)
            if self._consume_during_publish:
                event.status = "CONSUMED"
                event.claimed_at = None
                event.claim_token = None
                event.claimed_by = None
                event.published_at = NOW
                event.consumed_at = NOW
                event.consumer_attempt_count += 1
        self.calls.append(
            {"topic": topic, "payload": dict(payload), "correlation_id": correlation_id}
        )
        if self._fail:
            raise RuntimeError("broker unavailable")
        return str(payload["event_id"])

    def is_ready(self) -> bool:
        return True


def _factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _seed(
    factory: sessionmaker[Session],
    *,
    status: str = "PENDING",
    attempt_count: int = 0,
    claimed_at: datetime | None = None,
) -> tuple[UUID, UUID, UUID, UUID]:
    tenant_id, case_id, run_id, event_id = uuid4(), uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add(_Run(id=run_id, tenant_id=tenant_id, status="QUEUED"))
        session.add(
            _Outbox(
                id=event_id,
                tenant_id=tenant_id,
                case_id=case_id,
                run_id=run_id,
                correlation_id="corr-1",
                status=status,
                attempt_count=attempt_count,
                available_at=NOW,
                claimed_at=claimed_at,
                claim_token=uuid4() if claimed_at is not None else None,
                claimed_by="stale-dispatcher" if claimed_at is not None else None,
                created_at=NOW,
            )
        )
    return tenant_id, case_id, run_id, event_id


def _dispatcher(
    factory: sessionmaker[Session],
    queue: _Queue,
    clock: _Clock,
    *,
    max_attempts: int = 5,
) -> ReliableSQLAlchemyOutboxDispatcher:
    return ReliableSQLAlchemyOutboxDispatcher(
        session_factory=factory,
        queue=queue,
        spec=ReliableOutboxSpec(
            model=_Outbox,
            aggregate_id_attribute="run_id",
            queue_payload_key="run_id",
            topic="test.requested.v1",
            dispatch_failure_code="TEST_OUTBOX_FAILED",
            terminal_run_failure=TerminalRunFailure(
                model=_Run,
                id_attribute="id",
                failure_code="TEST_RUN_DISPATCH_FAILED",
                failure_message="Test run dispatch failed.",
            ),
        ),
        claimed_by="test-dispatcher",
        claim_ttl=timedelta(seconds=30),
        max_attempts=max_attempts,
        retry_base=timedelta(seconds=5),
        retry_max=timedelta(seconds=20),
        now_factory=clock,
    )


def test_exponential_retry_delay_is_bounded_and_validated() -> None:
    assert exponential_retry_delay(attempt_count=1) == timedelta(seconds=5)
    assert exponential_retry_delay(attempt_count=2) == timedelta(seconds=10)
    assert exponential_retry_delay(attempt_count=20) == timedelta(minutes=5)
    with pytest.raises(ValueError, match="attempt_count"):
        exponential_retry_delay(attempt_count=0)


def test_dispatch_claim_is_committed_before_publish_and_payload_shape_is_preserved() -> None:
    factory = _factory()
    tenant_id, case_id, run_id, event_id = _seed(factory)
    queue = _Queue(factory)

    result = _dispatcher(factory, queue, _Clock(NOW)).execute()

    assert result.model_dump() == {"claimed": 1, "published": 1, "retried": 0, "failed": 0}
    assert queue.observed_statuses == ["PROCESSING"]
    assert queue.calls == [
        {
            "topic": "test.requested.v1",
            "payload": {
                "event_id": str(event_id),
                "tenant_id": str(tenant_id),
                "case_id": str(case_id),
                "run_id": str(run_id),
                "correlation_id": "corr-1",
            },
            "correlation_id": "corr-1",
        }
    ]
    with factory() as session:
        event = session.get(_Outbox, event_id)
        assert event is not None
        assert event.status == "PUBLISHED"
        assert event.attempt_count == 1
        assert event.claim_token is None and event.claimed_at is None
        assert event.published_at == NOW.replace(tzinfo=None)


def test_publish_failure_uses_backoff_then_persists_terminal_failure() -> None:
    factory = _factory()
    tenant_id, _, run_id, event_id = _seed(factory)
    clock = _Clock(NOW)
    queue = _Queue(factory, fail=True)
    dispatcher = _dispatcher(factory, queue, clock, max_attempts=2)

    first = dispatcher.execute()
    assert first.model_dump() == {"claimed": 1, "published": 0, "retried": 1, "failed": 0}
    with factory() as session:
        event = session.get(_Outbox, event_id)
        assert event is not None
        assert event.status == "PENDING"
        assert event.available_at == (NOW + timedelta(seconds=5)).replace(tzinfo=None)
        assert event.claim_token is None
        assert event.last_error == "Message publication failed; retry scheduled."

    clock.value = NOW + timedelta(seconds=5)
    second = dispatcher.execute()
    assert second.model_dump() == {"claimed": 1, "published": 0, "retried": 0, "failed": 1}
    with factory() as session:
        event = session.scalars(
            select(_Outbox).where(_Outbox.id == event_id, _Outbox.tenant_id == tenant_id)
        ).one()
        run = session.get(_Run, run_id)
        assert event.status == "FAILED"
        assert event.attempt_count == 2
        assert event.failure_code == "TEST_OUTBOX_FAILED"
        assert event.failed_at == clock.value.replace(tzinfo=None)
        assert run is not None and run.status == "FAILED"
        assert run.failure_code == "TEST_RUN_DISPATCH_FAILED"


def test_stale_processing_claim_is_recovered_and_late_publisher_is_fenced() -> None:
    factory = _factory()
    _, _, _, event_id = _seed(
        factory,
        status="PROCESSING",
        attempt_count=1,
        claimed_at=NOW - timedelta(seconds=31),
    )
    queue = _Queue(factory, consume_during_publish=True)

    result = _dispatcher(factory, queue, _Clock(NOW)).execute()

    assert result.model_dump() == {"claimed": 1, "published": 0, "retried": 0, "failed": 0}
    with factory() as session:
        event = session.get(_Outbox, event_id)
        assert event is not None
        assert event.status == "CONSUMED"
        assert event.attempt_count == 2
        assert event.consumer_attempt_count == 1
        assert event.claim_token is None


def test_terminal_publish_failure_fails_an_expired_running_aggregate() -> None:
    factory = _factory()
    _, _, run_id, event_id = _seed(
        factory,
        status="PROCESSING",
        attempt_count=1,
        claimed_at=NOW - timedelta(seconds=31),
    )
    worker_claim = uuid4()
    with factory.begin() as session:
        run = session.get(_Run, run_id)
        assert run is not None
        run.status = "RUNNING"
        run.started_at = NOW - timedelta(minutes=1)
        run.execution_attempt_count = 1
        run.claim_token = worker_claim
        run.lease_expires_at = NOW - timedelta(seconds=1)

    result = _dispatcher(factory, _Queue(factory, fail=True), _Clock(NOW), max_attempts=2).execute()

    assert result.model_dump() == {"claimed": 1, "published": 0, "retried": 0, "failed": 1}
    with factory() as session:
        event = session.get(_Outbox, event_id)
        run = session.get(_Run, run_id)
        assert event is not None and event.status == "FAILED"
        assert run is not None and run.status == "FAILED"
        assert run.claim_token is None and run.lease_expires_at is None
        assert run.failure_code == "TEST_RUN_DISPATCH_FAILED"


def test_terminal_publish_failure_preserves_an_active_broker_copy_lease() -> None:
    factory = _factory()
    _, _, run_id, event_id = _seed(
        factory,
        status="PROCESSING",
        attempt_count=1,
        claimed_at=NOW - timedelta(seconds=31),
    )
    worker_claim = uuid4()
    active_lease = NOW + timedelta(minutes=1)
    with factory.begin() as session:
        run = session.get(_Run, run_id)
        assert run is not None
        run.status = "RUNNING"
        run.started_at = NOW - timedelta(seconds=10)
        run.execution_attempt_count = 1
        run.claim_token = worker_claim
        run.lease_expires_at = active_lease

    result = _dispatcher(factory, _Queue(factory, fail=True), _Clock(NOW), max_attempts=2).execute()

    assert result.model_dump() == {"claimed": 1, "published": 0, "retried": 0, "failed": 1}
    with factory() as session:
        event = session.get(_Outbox, event_id)
        run = session.get(_Run, run_id)
        assert event is not None and event.status == "FAILED"
        assert event.failure_code == "TEST_OUTBOX_FAILED"
        assert run is not None and run.status == "RUNNING"
        assert run.claim_token == worker_claim
        assert run.lease_expires_at == active_lease.replace(tzinfo=None)


def test_revision_0012_is_linear_and_models_expose_reliability_columns() -> None:
    config = Config()
    config.set_main_option("script_location", str(Path("alembic")))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20260827_0012_async_reliability")
    assert revision is not None
    assert revision.down_revision == "20260827_0011_human_review"
    assert scripts.get_heads() == ["20260827_0012_async_reliability"]

    run_columns = {"execution_attempt_count", "claim_token", "lease_expires_at"}
    for model in (
        PolicyRetrievalRunModel,
        GroundedExplanationRunModel,
        PolicyEvaluationRunModel,
    ):
        assert run_columns <= set(model.__table__.columns.keys())

    outbox_columns = {
        "claimed_at",
        "claim_token",
        "claimed_by",
        "published_at",
        "last_error",
        "consumed_at",
        "consumer_attempt_count",
        "consumer_last_error",
        "failure_code",
        "failed_at",
    }
    for model in (
        PolicyRetrievalOutboxEventModel,
        GroundedExplanationOutboxEventModel,
        PolicyEvaluationOutboxEventModel,
        HumanReviewRequestEventModel,
    ):
        assert outbox_columns <= set(model.__table__.columns.keys())

    migration = Path("alembic/versions/20260827_0012_async_reliability.py")
    tree = ast.parse(migration.read_text(encoding="utf-8"), filename=str(migration))
    namespace: dict[str, Any] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
            and node.value is not None
        ):
            namespace[node.target.id] = ast.literal_eval(node.value)
    assert namespace == {
        "revision": "20260827_0012_async_reliability",
        "down_revision": "20260827_0011_human_review",
    }
    source = migration.read_text(encoding="utf-8")
    assert "_prepare_downgrade_active_state()" in source
    assert "Recovered stale dispatcher claim for 0011 downgrade." in source
    assert "WHERE status = 'RUNNING'" in source


def test_revision_0012_declares_human_review_and_run_case_integrity_contracts() -> None:
    source = Path("alembic/versions/20260827_0012_async_reliability.py").read_text(encoding="utf-8")

    for name in (
        "ck_human_review_tasks_assignee_status_consistent",
        "ck_human_review_decision_basis_typed_reference_consistent",
        "uq_policy_citation_pack_items_tenant_id_clause",
        "fk_human_review_decision_basis_citation_clause",
        "uq_policy_retrieval_runs_tenant_case_id",
        "fk_policy_retrieval_outbox_run_case",
        "uq_grounded_explanation_runs_tenant_case_id",
        "fk_grounded_explanation_outbox_run_case",
        "uq_policy_evaluation_runs_tenant_case_id",
        "fk_policy_evaluation_outbox_run_case",
        "fk_human_review_request_events_policy_run_case",
    ):
        assert name in source

    assert "SET released_at = task.resolved_at" in source
    assert "SET current_assignee_id = NULL" in source
    assert "SET current_assignee_id = decision.decided_by" in source
    assert "status = 'CLAIMED' AND current_assignee_id IS NOT NULL" in source
    assert "status IN ('CLAIMED','RESOLVED') AND current_assignee_id IS NOT NULL" in source
