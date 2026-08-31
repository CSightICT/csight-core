"""Disposable PostgreSQL proof for migration 0031 provider logout capabilities."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from alembic import command
from app.bootstrap.settings import Settings
from app.platform.oidc import oidc_provider_binding_hash

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260830_0030_case_source_scope"
REVISION = "20260830_0031_oidc_backchannel_logout"
ISSUER = "https://idp.example.test"
SUBJECT = "provider-subject"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0031")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0031 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0031 integration tests require PostgreSQL")

    database_name = f"csight_oidc_0031_{uuid4().hex[:16]}"
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
        admin_engine.dispose()


def _seed_legacy_session(engine: Engine) -> tuple[str, str]:
    tenant_id = uuid4()
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'OIDC')"),
            {"id": tenant_id, "slug": f"oidc-{tenant_id.hex[:12]}"},
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, tenant_id, email, password_hash, display_name) "
                "VALUES (:id, :tenant_id, :email, 'hash', 'OIDC Reviewer')"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"oidc-{user_id.hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO oidc_sessions "
                "(id, session_id_hash, csrf_token_hash, tenant_id, user_id, "
                "provider_issuer, provider_subject, created_at, last_seen_at, "
                "idle_expires_at, absolute_expires_at) VALUES "
                "(:id, :session_hash, :csrf_hash, :tenant_id, :user_id, :issuer, "
                ":subject, :now, :now, :idle, :absolute)"
            ),
            {
                "id": session_id,
                "session_hash": "a" * 64,
                "csrf_hash": "b" * 64,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "issuer": ISSUER,
                "subject": SUBJECT,
                "now": now,
                "idle": now + timedelta(minutes=30),
                "absolute": now + timedelta(hours=8),
            },
        )
    return str(session_id), oidc_provider_binding_hash(ISSUER, SUBJECT)


def test_upgrade_backfills_hash_and_provider_capability_revokes_without_tenant_context(
    migration_database: MigrationDatabase,
) -> None:
    session_id, subject_hash = _seed_legacy_session(migration_database.engine)
    command.upgrade(migration_database.config, REVISION)

    assert "oidc_logout_events" in inspect(migration_database.engine).get_table_names()
    with migration_database.engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT provider_subject_hash FROM oidc_sessions WHERE id = :id"),
                {"id": session_id},
            )
            == subject_hash
        )

    with migration_database.engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_api_role"))
        assert connection.scalar(text("SELECT count(*) FROM oidc_sessions")) == 0
        connection.execute(
            text("SELECT set_config('app.oidc_logout_subject_hash', :subject_hash, true)"),
            {"subject_hash": subject_hash},
        )
        updated = connection.execute(
            text(
                "UPDATE oidc_sessions SET revoked_at = now(), "
                "revocation_reason = 'OIDC_BACKCHANNEL_LOGOUT' "
                "WHERE revoked_at IS NULL"
            )
        )
        assert updated.rowcount == 1
        connection.execute(
            text(
                "INSERT INTO oidc_logout_events "
                "(id, provider_issuer, provider_subject_hash, token_jti_hash, "
                "received_at, revoked_session_count) VALUES "
                "(:id, :issuer, :subject_hash, :jti_hash, now(), 1)"
            ),
            {
                "id": uuid4(),
                "issuer": ISSUER,
                "subject_hash": subject_hash,
                "jti_hash": "c" * 64,
            },
        )
        with pytest.raises(SQLAlchemyError):
            connection.scalar(text("SELECT count(*) FROM oidc_logout_events"))

    command.upgrade(migration_database.config, "head")
    command.check(migration_database.config)
