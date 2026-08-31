"""Disposable PostgreSQL proof that RLS survives omitted app predicates."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.persistence.engine import (
    DatabaseConfigurationError,
    clear_engine_cache,
    get_engine,
)
from app.adapters.persistence.tenant_context import TenantAwareSession, tenant_context
from app.bootstrap.settings import Settings
from scripts.provision_postgres_runtime_logins import RuntimeLogin, provision_runtime_logins

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260829_0019_analysis_execution_modes"
REVISION = "20260829_0020_postgres_rls_roles"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def rls_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test PostgreSQL RLS")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for PostgreSQL RLS integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("PostgreSQL RLS integration tests require PostgreSQL")

    database_name = f"csight_rls_0020_{uuid4().hex[:16]}"
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


def _seed_two_tenants(engine: Engine) -> tuple[tuple[UUID, UUID], tuple[UUID, UUID]]:
    tenant_ids = (uuid4(), uuid4())
    user_ids: list[UUID] = []
    with engine.begin() as connection:
        for index, tenant_id in enumerate(tenant_ids, start=1):
            user_id = uuid4()
            user_ids.append(user_id)
            connection.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
                {
                    "id": tenant_id,
                    "slug": f"rls-tenant-{index}-{tenant_id.hex[:8]}",
                    "name": f"RLS Tenant {index}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, tenant_id, email, password_hash, display_name) "
                    "VALUES (:id, :tenant_id, :email, 'hash', 'RLS User')"
                ),
                {
                    "id": user_id,
                    "tenant_id": tenant_id,
                    "email": f"rls-{user_id.hex}@example.test",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO cases "
                    "(id, tenant_id, order_ref, product_ref, customer_message, "
                    " requested_action, attributes, created_by) "
                    "VALUES (:id, :tenant_id, :order_ref, 'PRODUCT', 'synthetic', "
                    " 'UNSPECIFIED', '{}'::jsonb, :user_id)"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "order_ref": f"ORDER-{index}",
                    "user_id": user_id,
                },
            )
    return tenant_ids, (user_ids[0], user_ids[1])


def test_api_role_rls_denies_missing_context_and_omitted_predicate(
    rls_database: MigrationDatabase,
) -> None:
    command.upgrade(rls_database.config, REVISION)
    (first_tenant, second_tenant), (_, second_user) = _seed_two_tenants(rls_database.engine)

    with rls_database.engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_api_role"))
        assert connection.scalar(text("SELECT count(*) FROM cases")) == 0
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(first_tenant)},
        )
        # Deliberately omit every application tenant predicate. PostgreSQL still
        # returns only the transaction's authenticated tenant.
        assert connection.scalar(text("SELECT count(*) FROM cases")) == 1
        assert (
            connection.scalar(
                text("SELECT count(*) FROM cases WHERE tenant_id = :tenant_id"),
                {"tenant_id": second_tenant},
            )
            == 0
        )

    with rls_database.engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_api_role"))
        with tenant_context(str(first_tenant)), TenantAwareSession(bind=connection) as session:
            # The adapter's after-BEGIN hook applies set_config(..., true); no
            # repository WHERE predicate is needed for the database proof.
            assert session.scalar(text("SELECT count(*) FROM cases")) == 1

    with rls_database.engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_api_role"))
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(first_tenant)},
        )
        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text(
                    "INSERT INTO cases "
                    "(id, tenant_id, order_ref, product_ref, customer_message, "
                    " requested_action, attributes, created_by) "
                    "VALUES (:id, :wrong_tenant, 'CROSS-TENANT', 'PRODUCT', 'synthetic', "
                    "'UNSPECIFIED', '{}'::jsonb, :created_by)"
                ),
                {
                    "id": uuid4(),
                    "wrong_tenant": second_tenant,
                    "created_by": second_user,
                },
            )


def test_dispatcher_role_can_only_read_outbox_scope(
    rls_database: MigrationDatabase,
) -> None:
    with rls_database.engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_dispatcher_role"))
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 0
        with pytest.raises(SQLAlchemyError):
            connection.scalar(text("SELECT count(*) FROM cases"))


def test_required_runtime_guard_rejects_owner_bypass_login(
    rls_database: MigrationDatabase,
) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr(rls_database.engine.url.render_as_string(hide_password=False)),
        database_runtime_role="api",
        database_rls_required=True,
    )
    clear_engine_cache()
    try:
        guarded_engine = get_engine(settings)
        with (
            pytest.raises(DatabaseConfigurationError, match="non-bypass runtime role"),
            guarded_engine.connect(),
        ):
            pass
    finally:
        clear_engine_cache()


def test_distinct_runtime_logins_connect_through_secret_files(
    rls_database: MigrationDatabase,
    tmp_path: Path,
) -> None:
    command.upgrade(rls_database.config, REVISION)
    suffix = uuid4().hex[:12]
    login_specs = (
        ("api", f"csight_api_test_{suffix}", "csight_api_role"),
        ("worker", f"csight_worker_test_{suffix}", "csight_worker_role"),
        ("dispatcher", f"csight_dispatch_test_{suffix}", "csight_dispatcher_role"),
    )
    runtime_logins: list[RuntimeLogin] = []
    for index, (process, login_name, group_role) in enumerate(login_specs, start=1):
        password_file = tmp_path / f"{process}-password"
        password_file.write_text(f"runtime-{index}-{'x' * 32}", encoding="utf-8")
        password_file.chmod(0o600)
        runtime_logins.append(
            RuntimeLogin(
                process=process,
                login_name=login_name,
                group_role=group_role,
                password_file=password_file,
            )
        )

    owner_url = rls_database.engine.url.render_as_string(hide_password=False)
    provision_runtime_logins(owner_url, tuple(runtime_logins))
    try:
        for runtime_login in runtime_logins:
            owner = rls_database.engine.url
            passwordless_url = URL.create(
                drivername=owner.drivername,
                username=runtime_login.login_name,
                host=owner.host,
                port=owner.port,
                database=owner.database,
                query=owner.query,
            ).render_as_string(hide_password=False)
            settings = Settings(
                _env_file=None,  # pyright: ignore[reportCallIssue]
                database_url=SecretStr(passwordless_url),
                database_password_file=runtime_login.password_file,
                database_runtime_role=runtime_login.process,
                database_rls_required=True,
            )
            clear_engine_cache()
            guarded_engine = get_engine(settings)
            with guarded_engine.connect() as connection:
                assert connection.scalar(text("SELECT current_user")) == runtime_login.login_name
                if runtime_login.process == "dispatcher":
                    assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 0
                    with pytest.raises(SQLAlchemyError):
                        connection.scalar(text("SELECT count(*) FROM cases"))
                else:
                    assert connection.scalar(text("SELECT count(*) FROM cases")) == 0
    finally:
        clear_engine_cache()
        with rls_database.engine.begin() as connection:
            for runtime_login in runtime_logins:
                connection.execute(text(f'DROP ROLE IF EXISTS "{runtime_login.login_name}"'))


def test_rls_migration_round_trip(rls_database: MigrationDatabase) -> None:
    command.downgrade(rls_database.config, PREVIOUS)
    command.upgrade(rls_database.config, REVISION)
    with rls_database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
