"""Disposable PostgreSQL gates for privacy lifecycle migration 0022."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from alembic import command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260829_0021_failure_recovery"
REVISION = "20260829_0022_privacy_lifecycle"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0022")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0022 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0022 integration tests require PostgreSQL")

    database_name = f"csight_migration_0022_{uuid4().hex[:16]}"
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


def _insert_case_without_payload(engine: Engine) -> tuple[UUID, UUID, UUID, datetime, str]:
    tenant_id, user_id, case_id = uuid4(), uuid4(), uuid4()
    created_at = datetime.now(UTC)
    message = "synthetic migration payload"
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Migration')"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id.hex}"},
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
                "(id, tenant_id, order_ref, product_ref, customer_message, requested_action, "
                " attributes, created_by, created_at, updated_at) "
                "VALUES (:id, :tenant_id, 'ORDER', 'PRODUCT', :message, 'UNSPECIFIED', "
                " '{}'::jsonb, :user_id, :created_at, :created_at)"
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message": message,
                "created_at": created_at,
            },
        )
    return tenant_id, user_id, case_id, created_at, message


def _insert_payload(
    engine: Engine,
    *,
    tenant_id: UUID,
    case_id: UUID,
    created_at: datetime,
    message: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO case_sensitive_payloads "
                "(id, tenant_id, case_id, schema_version, customer_message, payload_sha256, "
                " retention_policy_version, expires_at, purged_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :case_id, 'case_sensitive_payload/1.0.0', "
                " :message, :digest, 'migration/30d', :expires_at, NULL, :created_at, :created_at)"
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "message": message,
                "digest": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                "expires_at": created_at + timedelta(days=30),
                "created_at": created_at,
            },
        )


def test_upgrade_fails_closed_until_backfill_and_dual_write_are_consistent(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    tenant_id, _user_id, case_id, created_at, message = _insert_case_without_payload(engine)

    with pytest.raises(DBAPIError, match="missing sensitive payload rows"):
        command.upgrade(config, REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS

    _insert_payload(
        engine,
        tenant_id=tenant_id,
        case_id=case_id,
        created_at=created_at,
        message="different synthetic payload",
    )
    with pytest.raises(DBAPIError, match="dual-write parity mismatch"):
        command.upgrade(config, REVISION)

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE case_sensitive_payloads "
                "SET customer_message = :message, payload_sha256 = :digest "
                "WHERE tenant_id = :tenant_id AND case_id = :case_id"
            ),
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "message": message,
                "digest": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            },
        )

    command.upgrade(config, REVISION)
    columns = {item["name"] for item in inspect(engine).get_columns("case_sensitive_payloads")}
    assert "legacy_redacted_at" in columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
        assert not connection.scalar(
            text("SELECT has_table_privilege('csight_api_role', 'data_lifecycle_events', 'UPDATE')")
        )
        assert not connection.scalar(
            text(
                "SELECT has_table_privilege("
                "'csight_worker_role', 'data_lifecycle_events', 'DELETE')"
            )
        )

    with engine.begin() as connection:
        savepoint = connection.begin_nested()
        try:
            with pytest.raises(DBAPIError, match="dual-write mismatch"):
                connection.execute(
                    text(
                        "UPDATE cases SET customer_message = 'drift' "
                        "WHERE tenant_id = :tenant_id AND id = :case_id"
                    ),
                    {"tenant_id": tenant_id, "case_id": case_id},
                )
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        finally:
            if savepoint.is_active:
                savepoint.rollback()

    command.downgrade(config, PREVIOUS)
    assert "legacy_redacted_at" not in {
        item["name"] for item in inspect(engine).get_columns("case_sensitive_payloads")
    }
    command.upgrade(config, REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
    command.upgrade(config, "head")
    command.check(config)
