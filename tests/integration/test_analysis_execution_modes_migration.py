"""Disposable PostgreSQL gates for analysis execution-mode migration 0019."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.persistence.analysis_repositories import SQLAlchemyAnalysisRunRepository
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260829_0018_oidc_sessions"
REVISION = "20260829_0019_analysis_execution_modes"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0019")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0019 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0019 integration tests require PostgreSQL")

    database_name = f"csight_migration_0019_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    temporary_engine: Engine | None = None
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
        command.upgrade(config, PREVIOUS)
        temporary_engine = create_engine(
            temporary_url,
            pool_pre_ping=True,
            poolclass=NullPool,
        )
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                        {"name": database_name},
                    )
                    == 0
                )
        admin_engine.dispose()


def _insert_analysis_fixture(engine: Engine) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    tenant_id, user_id, case_id, primary_id, shadow_id = (uuid4() for _ in range(5))
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id.hex}", "name": "Migration"},
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, tenant_id, email, password_hash, display_name) "
                "VALUES (:id, :tenant_id, :email, 'hash', 'Migration User')"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"migration-{user_id.hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO cases "
                "(id, tenant_id, order_ref, product_ref, customer_message, "
                " requested_action, attributes, created_by) "
                "VALUES (:id, :tenant_id, 'ORDER', 'PRODUCT', 'synthetic case', "
                " 'UNSPECIFIED', '{}'::jsonb, :user_id)"
            ),
            {"id": case_id, "tenant_id": tenant_id, "user_id": user_id},
        )
        customer_message = "synthetic case"
        connection.execute(
            text(
                "INSERT INTO case_sensitive_payloads "
                "(id, tenant_id, case_id, schema_version, customer_message, payload_sha256, "
                " retention_policy_version, expires_at, purged_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :case_id, 'case_sensitive_payload/1.0.0', "
                " :customer_message, :payload_sha256, 'integration/30d', :expires_at, NULL, "
                " :now, :now)"
            ),
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "case_id": case_id,
                "customer_message": customer_message,
                "payload_sha256": hashlib.sha256(customer_message.encode()).hexdigest(),
                "expires_at": now + timedelta(days=30),
                "now": now,
            },
        )
        base = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "requested_by": user_id,
            "now": now,
        }
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id, tenant_id, case_id, pipeline_name, pipeline_version, trigger_type, "
                " status, requested_by, correlation_id, idempotency_key, request_hash, "
                " requested_at) VALUES "
                "(:id, :tenant_id, :case_id, 'product_defect_text_extraction', '1.0.0', "
                " 'USER_REQUEST', 'QUEUED', :requested_by, 'corr-primary', "
                " 'primary-key', :request_hash, :now)"
            ),
            {**base, "id": primary_id, "request_hash": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id, tenant_id, case_id, pipeline_name, pipeline_version, execution_mode, "
                " trigger_type, status, requested_by, correlation_id, idempotency_key, "
                " request_hash, requested_at) VALUES "
                "(:id, :tenant_id, :case_id, 'product_defect_text_extraction', '1.0.0', "
                " 'SHADOW', 'USER_REQUEST', 'QUEUED', :requested_by, 'corr-shadow', "
                " 'shadow-key', :request_hash, :now)"
            ),
            {**base, "id": shadow_id, "request_hash": "b" * 64},
        )
    return tenant_id, user_id, case_id, primary_id, shadow_id


def test_migration_round_trip_and_shadow_database_guards(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    command.upgrade(config, REVISION)
    columns = {column["name"]: column for column in inspect(engine).get_columns("analysis_runs")}
    assert columns["execution_mode"]["nullable"] is False
    assert "PRIMARY" in str(columns["execution_mode"]["default"])
    assert "ix_analysis_runs_admission_nonterminal" in {
        item["name"] for item in inspect(engine).get_indexes("analysis_runs")
    }

    tenant_id, _, case_id, primary_id, shadow_id = _insert_analysis_fixture(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT execution_mode FROM analysis_runs WHERE id = :id"),
                {"id": primary_id},
            )
            == "PRIMARY"
        )

    with engine.begin() as connection:
        savepoint = connection.begin_nested()
        try:
            with pytest.raises(IntegrityError) as immutable:
                connection.execute(
                    text("UPDATE analysis_runs SET execution_mode = 'SHADOW' WHERE id = :id"),
                    {"id": primary_id},
                )
            immutable_diagnostic = getattr(immutable.value.orig, "diag", None)
            assert immutable_diagnostic is not None
            assert getattr(immutable_diagnostic, "constraint_name", None) == (
                "ck_analysis_runs_execution_mode_immutable"
            )
        finally:
            savepoint.rollback()

        savepoint = connection.begin_nested()
        try:
            with pytest.raises(IntegrityError) as downstream:
                connection.execute(
                    text(
                        "INSERT INTO policy_evaluation_runs "
                        "(id, tenant_id, case_id, analysis_run_id) "
                        "VALUES (:id, :tenant_id, :case_id, :analysis_run_id)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": tenant_id,
                        "case_id": case_id,
                        "analysis_run_id": shadow_id,
                    },
                )
            downstream_diagnostic = getattr(downstream.value.orig, "diag", None)
            assert downstream_diagnostic is not None
            assert getattr(downstream_diagnostic, "constraint_name", None) == (
                "ck_shadow_analysis_no_downstream"
            )
        finally:
            savepoint.rollback()

    with Session(engine) as first_session:
        first_counts = SQLAlchemyAnalysisRunRepository(first_session).lock_admission_counts(
            tenant_id=str(tenant_id)
        )
        assert first_counts.global_nonterminal == 2
        assert first_counts.tenant_nonterminal == 2

        competing_started = Event()

        def acquire_competing_admission() -> tuple[int, int]:
            with Session(engine) as competing_session:
                competing_started.set()
                counts = SQLAlchemyAnalysisRunRepository(competing_session).lock_admission_counts(
                    tenant_id=str(tenant_id)
                )
                competing_session.rollback()
                return counts.global_nonterminal, counts.tenant_nonterminal

        with ThreadPoolExecutor(max_workers=1) as executor:
            competing = executor.submit(acquire_competing_admission)
            assert competing_started.wait(timeout=2)
            with pytest.raises(FutureTimeoutError):
                competing.result(timeout=0.2)
            first_session.rollback()
            assert competing.result(timeout=2) == (2, 2)

    command.downgrade(config, PREVIOUS)
    assert "execution_mode" not in {
        column["name"] for column in inspect(engine).get_columns("analysis_runs")
    }
    command.upgrade(config, REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
    command.upgrade(config, "head")
    command.check(config)
