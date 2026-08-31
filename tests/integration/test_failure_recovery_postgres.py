"""Disposable PostgreSQL proof for strict-role durable failure recovery."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.persistence.failure_recovery import SQLAlchemyOperationalFailureRepository
from app.adapters.persistence.failure_recovery_outbox import (
    DispatchOperationalFailureRecoveryOutbox,
)
from app.adapters.persistence.tenant_context import TenantAwareSession, tenant_context
from app.bootstrap.settings import Settings
from app.platform.errors import (
    IdempotencyKeyReusedError,
    OperationalFailureAlreadyResolvedError,
)
from app.platform.tenant_context import case_access_context

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REVISION = "20260829_0021_failure_recovery"
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RecoveryDatabase:
    config: Config
    owner_engine: Engine
    api_engine: Engine
    dispatcher_engine: Engine


@dataclass(frozen=True, slots=True)
class SeededFailure:
    tenant_id: UUID
    user_id: UUID
    case_id: UUID
    run_id: UUID
    stage_id: UUID
    event_id: UUID
    failure_id: UUID


def _role_engine(url: str | URL, role: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True, poolclass=NullPool)

    def set_local_role(connection: Connection) -> None:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")

    event.listen(engine, "begin", set_local_role)
    return engine


@pytest.fixture(scope="module")
def recovery_database() -> Generator[RecoveryDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test PostgreSQL failure recovery")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for PostgreSQL failure recovery tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("PostgreSQL failure recovery tests require PostgreSQL")

    database_name = f"csight_failure_0021_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    engines: list[Engine] = []
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True
        temporary_url = source_url.set(database=database_name)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            temporary_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        # Repository behavior must run against the current ORM/migration head.
        # The final test below still exercises the original 0021 round trip explicitly.
        command.upgrade(config, "head")
        owner_engine = create_engine(
            temporary_url,
            pool_pre_ping=True,
            poolclass=NullPool,
        )
        api_engine = _role_engine(temporary_url, "csight_api_role")
        dispatcher_engine = _role_engine(temporary_url, "csight_dispatcher_role")
        engines.extend((owner_engine, api_engine, dispatcher_engine))
        yield RecoveryDatabase(
            config=config,
            owner_engine=owner_engine,
            api_engine=api_engine,
            dispatcher_engine=dispatcher_engine,
        )
    finally:
        for engine in engines:
            engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
        admin_engine.dispose()


def _seed_tenant(engine: Engine, *, ordinal: int) -> tuple[UUID, UUID]:
    tenant_id, user_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {
                "id": tenant_id,
                "slug": f"failure-tenant-{ordinal}-{tenant_id.hex[:8]}",
                "name": f"Failure Tenant {ordinal}",
            },
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, tenant_id, email, password_hash, display_name) "
                "VALUES (:id, :tenant_id, :email, 'hash', 'Failure Admin')"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"failure-{user_id.hex}@example.test",
            },
        )
    return tenant_id, user_id


def _seed_analysis_outbox(
    engine: Engine,
    *,
    tenant_id: UUID,
    user_id: UUID,
    ordinal: int,
) -> tuple[UUID, UUID, UUID, UUID]:
    case_id, run_id, stage_id, event_id = uuid4(), uuid4(), uuid4(), uuid4()
    correlation_id = f"failure-corr-{ordinal}-{uuid4()}"
    payload = {
        "event_id": str(event_id),
        "event_type": "analysis.requested.v1",
        "event_version": "1.0",
        "tenant_id": str(tenant_id),
        "case_id": str(case_id),
        "analysis_run_id": str(run_id),
        "stage_run_id": str(stage_id),
        "correlation_id": correlation_id,
        "occurred_at": NOW.isoformat(),
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cases "
                "(id, tenant_id, order_ref, product_ref, customer_message, requested_action, "
                " attributes, source_scope, source_provenance, created_by) VALUES "
                "(:id, :tenant_id, :order_ref, 'SYNTHETIC', 'synthetic test only', "
                " 'UNSPECIFIED', '{}'::jsonb, 'SYNTHETIC_DEMO', "
                " 'failure-recovery-integration', :user_id)"
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "order_ref": f"FAILURE-{ordinal}-{case_id.hex[:8]}",
                "user_id": user_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO case_sensitive_payloads "
                "(id, tenant_id, case_id, schema_version, customer_message, payload_sha256, "
                " retention_policy_version, expires_at, purged_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :case_id, 'case_sensitive_payload/1.0.0', "
                " 'synthetic test only', :payload_sha256, 'integration/30d', :expires_at, "
                " NULL, :now, :now)"
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "payload_sha256": hashlib.sha256(b"synthetic test only").hexdigest(),
                "expires_at": NOW + timedelta(days=30),
                "now": NOW,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id, tenant_id, case_id, pipeline_name, pipeline_version, trigger_type, "
                " status, requested_by, correlation_id, idempotency_key, request_hash, "
                " requested_at) VALUES "
                "(:id, :tenant_id, :case_id, 'product_defect_text_extraction', '1.0.0', "
                " 'USER_REQUEST', 'QUEUED', :requested_by, :correlation_id, "
                " :idempotency_key, :request_hash, :now)"
            ),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "requested_by": user_id,
                "correlation_id": correlation_id,
                "idempotency_key": f"failure-analysis-{ordinal}-{run_id}",
                "request_hash": f"{ordinal % 10}" * 64,
                "now": NOW,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_stage_runs "
                "(id, tenant_id, analysis_run_id, stage_type, status, attempt_count, "
                " provider_name, model_name, model_version, prompt_name, prompt_version, "
                " prompt_content_hash, input_schema_version, output_schema_version) VALUES "
                "(:id, :tenant_id, :run_id, 'TEXT_EXTRACTION', 'QUEUED', 0, "
                " 'mock', 'mock-model', '1.0.0', 'mock-prompt', '1.0.0', "
                " :prompt_hash, '1.0', '1.0')"
            ),
            {
                "id": stage_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "prompt_hash": "a" * 64,
            },
        )
        connection.execute(
            text(
                "INSERT INTO outbox_events "
                "(id, tenant_id, aggregate_type, aggregate_id, event_type, event_version, "
                " payload, status, attempt_count, available_at) VALUES "
                "(:id, :tenant_id, 'analysis_run', :run_id, 'analysis.requested.v1', '1.0', "
                " CAST(:payload AS jsonb), 'PENDING', 0, :now)"
            ),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "payload": json.dumps(payload),
                "now": NOW,
            },
        )
    return case_id, run_id, stage_id, event_id


def _mark_dispatch_failed(database: RecoveryDatabase, event_id: UUID) -> UUID:
    with database.dispatcher_engine.begin() as connection:
        updated = connection.execute(
            text(
                "UPDATE outbox_events SET status = 'FAILED', attempt_count = 5, "
                " claimed_at = NULL, claim_token = NULL, claimed_by = NULL, "
                " published_at = NULL, last_error = 'Message publication failed permanently.' "
                "WHERE id = :event_id"
            ),
            {"event_id": event_id},
        )
        assert updated.rowcount == 1
    with database.owner_engine.connect() as connection:
        failure_id = connection.scalar(
            text(
                "SELECT id FROM operational_failures "
                "WHERE source_table = 'outbox_events' AND source_event_id = :event_id"
            ),
            {"event_id": event_id},
        )
    assert isinstance(failure_id, UUID)
    return failure_id


def _seed_failure(
    database: RecoveryDatabase,
    *,
    tenant_id: UUID,
    user_id: UUID,
    ordinal: int,
) -> SeededFailure:
    case_id, run_id, stage_id, event_id = _seed_analysis_outbox(
        database.owner_engine,
        tenant_id=tenant_id,
        user_id=user_id,
        ordinal=ordinal,
    )
    return SeededFailure(
        tenant_id=tenant_id,
        user_id=user_id,
        case_id=case_id,
        run_id=run_id,
        stage_id=stage_id,
        event_id=event_id,
        failure_id=_mark_dispatch_failed(database, event_id),
    )


@pytest.fixture(scope="module")
def seeded_failures(
    recovery_database: RecoveryDatabase,
) -> tuple[SeededFailure, SeededFailure, SeededFailure]:
    first_tenant, first_user = _seed_tenant(recovery_database.owner_engine, ordinal=1)
    second_tenant, second_user = _seed_tenant(recovery_database.owner_engine, ordinal=2)
    replay_failure = _seed_failure(
        recovery_database,
        tenant_id=first_tenant,
        user_id=first_user,
        ordinal=1,
    )
    cancel_failure = _seed_failure(
        recovery_database,
        tenant_id=first_tenant,
        user_id=first_user,
        ordinal=2,
    )
    other_failure = _seed_failure(
        recovery_database,
        tenant_id=second_tenant,
        user_id=second_user,
        ordinal=3,
    )
    return replay_failure, cancel_failure, other_failure


def _api_factory(database: RecoveryDatabase) -> sessionmaker[Session]:
    return sessionmaker(
        bind=database.api_engine,
        class_=TenantAwareSession,
        expire_on_commit=False,
        autoflush=False,
    )


def test_strict_dispatcher_captures_failure_without_run_table_access(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    replay_failure, _, _ = seeded_failures
    with recovery_database.dispatcher_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 3
        with pytest.raises(SQLAlchemyError):
            connection.scalar(text("SELECT count(*) FROM analysis_runs"))

    with recovery_database.owner_engine.connect() as connection:
        failure = (
            connection.execute(
                text(
                    "SELECT pipeline, failure_kind, failure_code, replayable, correlation_id "
                    "FROM operational_failures WHERE id = :failure_id"
                ),
                {"failure_id": replay_failure.failure_id},
            )
            .mappings()
            .one()
        )
        run_status = connection.scalar(
            text("SELECT status FROM analysis_runs WHERE id = :run_id"),
            {"run_id": replay_failure.run_id},
        )
        stage_status = connection.scalar(
            text("SELECT status FROM analysis_stage_runs WHERE id = :stage_id"),
            {"stage_id": replay_failure.stage_id},
        )
    assert dict(failure) == {
        "pipeline": "analysis",
        "failure_kind": "DISPATCH",
        "failure_code": "OUTBOX_DISPATCH_FAILED",
        "replayable": True,
        "correlation_id": failure["correlation_id"],
    }
    assert str(failure["correlation_id"]).startswith("failure-corr-1-")
    # Strict Dispatcher mutates only its outbox. The queued execution remains
    # deliberately non-terminal until an authenticated replay or cancel action.
    assert run_status == "QUEUED"
    assert stage_status == "QUEUED"


def test_failure_rls_hides_missing_and_other_tenant_even_without_predicate(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    replay_failure, _, other_failure = seeded_failures
    with recovery_database.api_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM operational_failures")) == 0
    with recovery_database.api_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(replay_failure.tenant_id)},
        )
        # Deliberately omit the application tenant predicate.
        assert connection.scalar(text("SELECT count(*) FROM operational_failures")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM operational_failures WHERE tenant_id = :tenant_id"),
                {"tenant_id": other_failure.tenant_id},
            )
            == 0
        )


def test_replay_is_idempotent_append_only_and_references_original_failure(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    replay_failure, _, _ = seeded_failures
    repository = SQLAlchemyOperationalFailureRepository(
        _api_factory(recovery_database), now_factory=lambda: NOW
    )
    with (
        tenant_context(str(replay_failure.tenant_id)),
        case_access_context(str(replay_failure.user_id), can_view_all=True),
    ):
        page = repository.list_failures(
            tenant_id=str(replay_failure.tenant_id),
            since=NOW - timedelta(days=2),
            limit=100,
            cursor=None,
        )
        first = repository.replay_failure(
            tenant_id=str(replay_failure.tenant_id),
            failure_id=str(replay_failure.failure_id),
            actor_id=str(replay_failure.user_id),
            idempotency_key="postgres-replay-1",
            correlation_id="recovery-correlation-1",
        )
        repeated = repository.replay_failure(
            tenant_id=str(replay_failure.tenant_id),
            failure_id=str(replay_failure.failure_id),
            actor_id=str(replay_failure.user_id),
            idempotency_key="postgres-replay-1",
            correlation_id="recovery-correlation-1",
        )
        with pytest.raises(OperationalFailureAlreadyResolvedError):
            repository.replay_failure(
                tenant_id=str(replay_failure.tenant_id),
                failure_id=str(replay_failure.failure_id),
                actor_id=str(replay_failure.user_id),
                idempotency_key="postgres-replay-different",
                correlation_id="recovery-correlation-2",
            )
        with pytest.raises(IdempotencyKeyReusedError):
            repository.cancel_failure(
                tenant_id=str(replay_failure.tenant_id),
                failure_id=str(replay_failure.failure_id),
                actor_id=str(replay_failure.user_id),
                idempotency_key="postgres-replay-1",
                correlation_id="recovery-correlation-3",
            )

    assert {item.failure_id for item in page.items} >= {str(replay_failure.failure_id)}
    assert first.recovery_run_id is not None and first.recovery_event_id is not None
    assert repeated.recovery_run_id == first.recovery_run_id
    assert repeated.recovery_event_id == first.recovery_event_id
    assert repeated.idempotent_replay is True

    with recovery_database.owner_engine.connect() as connection:
        recovery = (
            connection.execute(
                text(
                    "SELECT run.failure_id, event.failure_id, event.recovery_run_id, "
                    "event.payload, "
                    " resolution.failure_id, resolution.recovery_run_id "
                    "FROM operational_failure_recovery_runs AS run "
                    "JOIN operational_failure_recovery_events AS event "
                    "  ON event.tenant_id = run.tenant_id AND event.recovery_run_id = run.id "
                    "JOIN operational_failure_resolutions AS resolution "
                    "  ON resolution.tenant_id = run.tenant_id "
                    " AND resolution.recovery_run_id = run.id "
                    "WHERE run.id = :run_id"
                ),
                {"run_id": UUID(first.recovery_run_id)},
            )
            .mappings()
            .one()
        )
        original = (
            connection.execute(
                text(
                    "SELECT event.status AS event_status, run.status AS run_status, "
                    " stage.status AS stage_status "
                    "FROM outbox_events AS event "
                    "JOIN analysis_runs AS run ON run.id = event.aggregate_id "
                    "JOIN analysis_stage_runs AS stage ON stage.analysis_run_id = run.id "
                    "WHERE event.id = :event_id"
                ),
                {"event_id": replay_failure.event_id},
            )
            .mappings()
            .one()
        )
    assert recovery["failure_id"] == replay_failure.failure_id
    assert recovery["recovery_run_id"] == UUID(first.recovery_run_id)
    assert recovery["payload"] == {
        "event_id": str(replay_failure.event_id),
        "tenant_id": str(replay_failure.tenant_id),
        "case_id": str(replay_failure.case_id),
        "analysis_run_id": str(replay_failure.run_id),
        "stage_run_id": str(replay_failure.stage_id),
        "correlation_id": recovery["payload"]["correlation_id"],
    }
    assert set(recovery["payload"]) == {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }
    assert dict(original) == {
        "event_status": "FAILED",
        "run_status": "QUEUED",
        "stage_status": "QUEUED",
    }

    with (
        pytest.raises(SQLAlchemyError, match="append-only"),
        recovery_database.owner_engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE operational_failures SET replayable = false WHERE id = :id"),
            {"id": replay_failure.failure_id},
        )


def test_cancel_is_terminal_auditable_and_fences_later_action(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    _, cancel_failure, _ = seeded_failures
    repository = SQLAlchemyOperationalFailureRepository(
        _api_factory(recovery_database), now_factory=lambda: NOW
    )
    with (
        tenant_context(str(cancel_failure.tenant_id)),
        case_access_context(str(cancel_failure.user_id), can_view_all=True),
    ):
        cancelled = repository.cancel_failure(
            tenant_id=str(cancel_failure.tenant_id),
            failure_id=str(cancel_failure.failure_id),
            actor_id=str(cancel_failure.user_id),
            idempotency_key="postgres-cancel-1",
            correlation_id="cancel-correlation-1",
        )
        repeated = repository.cancel_failure(
            tenant_id=str(cancel_failure.tenant_id),
            failure_id=str(cancel_failure.failure_id),
            actor_id=str(cancel_failure.user_id),
            idempotency_key="postgres-cancel-1",
            correlation_id="cancel-correlation-1",
        )
        with pytest.raises(IdempotencyKeyReusedError):
            repository.replay_failure(
                tenant_id=str(cancel_failure.tenant_id),
                failure_id=str(cancel_failure.failure_id),
                actor_id=str(cancel_failure.user_id),
                idempotency_key="postgres-cancel-1",
                correlation_id="cancel-correlation-2",
            )
        with pytest.raises(OperationalFailureAlreadyResolvedError):
            repository.replay_failure(
                tenant_id=str(cancel_failure.tenant_id),
                failure_id=str(cancel_failure.failure_id),
                actor_id=str(cancel_failure.user_id),
                idempotency_key="postgres-replay-after-cancel",
                correlation_id="cancel-correlation-3",
            )

    assert cancelled.action.value == "CANCELLED"
    assert cancelled.recovery_run_id is None and cancelled.recovery_event_id is None
    assert repeated.idempotent_replay is True
    with recovery_database.owner_engine.connect() as connection:
        statuses = (
            connection.execute(
                text(
                    "SELECT run.status AS run_status, stage.status AS stage_status, "
                    " run.failure_code AS run_failure, stage.failure_code AS stage_failure "
                    "FROM analysis_runs AS run "
                    "JOIN analysis_stage_runs AS stage ON stage.analysis_run_id = run.id "
                    "WHERE run.id = :run_id"
                ),
                {"run_id": cancel_failure.run_id},
            )
            .mappings()
            .one()
        )
        resolution = (
            connection.execute(
                text(
                    "SELECT action, reason_code, actor_id, recovery_run_id "
                    "FROM operational_failure_resolutions WHERE failure_id = :failure_id"
                ),
                {"failure_id": cancel_failure.failure_id},
            )
            .mappings()
            .one()
        )
    assert dict(statuses) == {
        "run_status": "FAILED",
        "stage_status": "FAILED",
        "run_failure": "OPERATIONAL_FAILURE_CANCELLED",
        "stage_failure": "OPERATIONAL_FAILURE_CANCELLED",
    }
    assert dict(resolution) == {
        "action": "CANCELLED",
        "reason_code": "OPERATOR_CANCELLED",
        "actor_id": cancel_failure.user_id,
        "recovery_run_id": None,
    }


class _CompetingPublisher:
    def __init__(self, owner_engine: Engine) -> None:
        self._owner_engine = owner_engine
        self.calls: list[dict[str, object]] = []

    def publish(
        self,
        *,
        topic: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> str:
        event_id = UUID(str(payload["event_id"]))
        self.calls.append(
            {"topic": topic, "payload": dict(payload), "correlation_id": correlation_id}
        )
        # Simulate a newer owner of the delivery completing before the stale
        # dispatcher writes its acknowledgement. Its claim token must fence it.
        with self._owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE operational_failure_recovery_events "
                    "SET status = 'PUBLISHED', claimed_at = NULL, claim_token = NULL, "
                    " claimed_by = NULL, published_at = :now "
                    "WHERE status = 'PROCESSING' AND payload->>'event_id' = :source_event_id"
                ),
                {"source_event_id": str(event_id), "now": NOW},
            )
        return str(event_id)

    def is_ready(self) -> bool:
        return True


def test_recovery_dispatch_claim_race_is_fenced_and_payload_stays_identifier_only(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    replay_failure, _, _ = seeded_failures
    publisher = _CompetingPublisher(recovery_database.owner_engine)
    factory = sessionmaker(
        bind=recovery_database.dispatcher_engine,
        class_=Session,
        expire_on_commit=False,
    )
    dispatcher = DispatchOperationalFailureRecoveryOutbox(
        session_factory=factory,
        queue=publisher,
        claimed_by="strict-dispatcher-test",
        now_factory=lambda: NOW,
        claim_token_factory=lambda: UUID("00000000-0000-4000-8000-000000000021"),
    )

    result = dispatcher.execute()

    assert result.model_dump() == {"claimed": 1, "published": 0, "retried": 0, "failed": 0}
    assert len(publisher.calls) == 1
    payload = publisher.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert set(payload) == {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }
    assert not set(payload) & {"customer_message", "email", "order_ref", "image_url"}
    with recovery_database.owner_engine.connect() as connection:
        status = connection.scalar(
            text(
                "SELECT status FROM operational_failure_recovery_events "
                "WHERE failure_id = :failure_id"
            ),
            {"failure_id": replay_failure.failure_id},
        )
    assert status == "PUBLISHED"


def test_failure_recovery_migration_round_trip(
    recovery_database: RecoveryDatabase,
    seeded_failures: tuple[SeededFailure, SeededFailure, SeededFailure],
) -> None:
    command.downgrade(recovery_database.config, "20260829_0020_postgres_rls_roles")
    command.upgrade(recovery_database.config, REVISION)
    with recovery_database.owner_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
    # Seed one explicit pre-privacy Case without a restricted payload.  The
    # following migration must stop rather than invent customer content.
    replay_failure, _, _ = seeded_failures
    with recovery_database.owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cases "
                "(id, tenant_id, order_ref, product_ref, customer_message, requested_action, "
                " attributes, created_by) VALUES "
                "(:id, :tenant_id, :order_ref, 'SYNTHETIC', 'missing payload sentinel', "
                " 'UNSPECIFIED', '{}'::jsonb, :user_id)"
            ),
            {
                "id": uuid4(),
                "tenant_id": replay_failure.tenant_id,
                "order_ref": f"MISSING-PAYLOAD-{uuid4().hex[:8]}",
                "user_id": replay_failure.user_id,
            },
        )
    with pytest.raises(SQLAlchemyError, match="missing sensitive payload rows"):
        command.upgrade(recovery_database.config, "head")
