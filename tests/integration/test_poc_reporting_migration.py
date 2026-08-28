"""Disposable PostgreSQL lifecycle gate for the Sprint 5C reporting schema."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REVISION_0013 = "20260827_0013_case_resolution_external_action"
REVISION_0014 = "20260827_0014_review_report_poc_metrics"
REVISION_HEAD = "20260828_0016_communication_learning_assets"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0014")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0014 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0014 integration tests require PostgreSQL")

    database_name = f"csight_migration_0014_{uuid4().hex[:16]}"
    admin_url = source_url.set(database="postgres")
    temporary_url = source_url.set(database=database_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True

        config = Config(str(ROOT / "alembic.ini"))
        migration_url = temporary_url.render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
        alembic_command.upgrade(config, REVISION_0013)
        temporary_engine = create_engine(temporary_url, pool_pre_ping=True, poolclass=NullPool)
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        try:
            if temporary_engine is not None:
                temporary_engine.dispose()
        finally:
            try:
                if created:
                    with admin_engine.connect() as connection:
                        quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                        connection.exec_driver_sql(
                            f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)"
                        )
                        remaining = connection.scalar(
                            text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                            {"name": database_name},
                        )
                        if remaining != 0:
                            raise RuntimeError("temporary migration 0014 database was not removed")
            finally:
                admin_engine.dispose()


def _constraints(engine: Engine, table_name: str) -> set[str]:
    schema = inspect(engine)
    return {
        str(item["name"])
        for item in (
            schema.get_check_constraints(table_name)
            + schema.get_foreign_keys(table_name)
            + schema.get_unique_constraints(table_name)
        )
        if item.get("name") is not None
    }


def test_review_report_migration_round_trip_and_drift(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    alembic_command.upgrade(config, REVISION_0014)

    schema = inspect(engine)
    assert "review_reports" in schema.get_table_names()
    assert {
        "fk_review_reports_resolution",
        "fk_review_reports_terminal_event",
        "ck_review_reports_resolution_version_positive",
        "ck_review_reports_schema_version_supported",
        "ck_review_reports_snapshots_object",
        "ck_review_reports_content_hash_valid",
        "uq_review_reports_resolution_version",
        "uq_review_reports_terminal_event",
    } <= _constraints(engine, "review_reports")
    assert "uq_case_resolution_events_tenant_case_resolution_id" in _constraints(
        engine, "case_resolution_events"
    )
    assert {
        "ck_external_action_simulation_request_events_attempts_valid",
        "ck_external_action_simulation_request_events_consumer_valid",
    } <= _constraints(engine, "external_action_simulation_request_events")
    assert "ck_external_action_simulation_attempts_failure_consistent" in _constraints(
        engine, "external_action_simulation_attempts"
    )
    assert "ck_external_action_simulation_results_outcome_consistent" in _constraints(
        engine, "external_action_simulation_results"
    )

    with engine.begin() as connection:
        report_table = Table(
            "review_reports",
            MetaData(),
            autoload_with=connection,
            resolve_fks=False,
        )
        savepoint = connection.begin_nested()
        try:
            with pytest.raises(IntegrityError) as captured:
                connection.execute(
                    report_table.insert(),
                    {
                        "id": uuid4(),
                        "tenant_id": uuid4(),
                        "case_id": uuid4(),
                        "resolution_id": uuid4(),
                        "resolution_version": 1,
                        "terminal_event_id": uuid4(),
                        "schema_version": "review_report/unsupported",
                        "case_snapshot": {},
                        "analysis_snapshot": {},
                        "policy_snapshot": {},
                        "review_snapshot": {},
                        "resolution_snapshot": {},
                        "dry_run_snapshot": {},
                        "qualification_snapshot": {},
                        "data_scope": {},
                        "generated_at": datetime.now(UTC),
                        "content_hash": "a" * 64,
                    },
                )
            diagnostic = getattr(captured.value.orig, "diag", None)
            assert diagnostic is not None
            assert diagnostic.constraint_name == "ck_review_reports_schema_version_supported"
        finally:
            savepoint.rollback()

    alembic_command.downgrade(config, REVISION_0013)
    schema = inspect(engine)
    assert "review_reports" not in schema.get_table_names()
    assert "uq_case_resolution_events_tenant_case_resolution_id" not in _constraints(
        engine, "case_resolution_events"
    )
    assert "ck_external_action_simulation_attempts_failure_fields_c_8797" in _constraints(
        engine, "external_action_simulation_attempts"
    )

    alembic_command.upgrade(config, REVISION_0014)
    alembic_command.upgrade(config, REVISION_HEAD)
    alembic_command.check(config)
    schema = inspect(engine)
    assert "customer_communication_simulations" in schema.get_table_names()
    assert "case_learning_assets" in schema.get_table_names()
    assert {
        "ck_customer_communication_simulations_no_external_effects",
        "uq_customer_communication_simulations_report_template",
    } <= _constraints(engine, "customer_communication_simulations")
    assert {
        "ck_case_learning_assets_snapshots_object",
        "uq_case_learning_assets_report_schema",
    } <= _constraints(engine, "case_learning_assets")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION_HEAD
