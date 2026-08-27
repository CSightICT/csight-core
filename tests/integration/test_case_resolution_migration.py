"""Disposable PostgreSQL lifecycle gate for Sprint 5C Resolution schema."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
REVISION_0012 = "20260827_0012_async_reliability"
REVISION_0013 = "20260827_0013_case_resolution_external_action"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0013")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0013 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0013 integration tests require PostgreSQL")

    database_name = f"csight_migration_0013_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    temporary_url = source_url.set(database=database_name)
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted} TEMPLATE template0")
            created = True
        config = Config(str(ROOT / "alembic.ini"))
        migration_url = temporary_url.render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
        alembic_command.upgrade(config, REVISION_0012)
        temporary_engine = create_engine(temporary_url, poolclass=NullPool)
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        try:
            if created:
                with admin_engine.connect() as connection:
                    quoted = connection.dialect.identifier_preparer.quote(database_name)
                    connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)")
                    assert (
                        connection.scalar(
                            text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                            {"name": database_name},
                        )
                        == 0
                    )
        finally:
            admin_engine.dispose()


def _constraint_names(engine: Engine, table: str) -> set[str]:
    schema = inspect(engine)
    return {
        str(item["name"])
        for item in (
            schema.get_check_constraints(table)
            + schema.get_foreign_keys(table)
            + schema.get_unique_constraints(table)
        )
        if item.get("name") is not None
    }


def test_0013_upgrade_downgrade_upgrade_round_trip(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    expected = {
        "case_resolutions",
        "case_resolution_events",
        "case_resolution_request_events",
        "external_action_intents",
        "external_action_simulation_request_events",
        "external_action_simulation_attempts",
        "external_action_simulation_results",
    }
    alembic_command.upgrade(config, REVISION_0013)
    assert expected <= set(inspect(engine).get_table_names())
    assert {
        "ck_external_action_intents_dry_run_only",
        "ck_external_action_intents_typed_input_consistent",
        "uq_external_action_intents_resolution",
    } <= _constraint_names(engine, "external_action_intents")
    assert {
        "ck_case_resolution_request_events_state_consistent",
        "fk_case_resolution_request_events_resolution",
        "uq_case_resolution_request_events_decision",
    } <= _constraint_names(engine, "case_resolution_request_events")

    alembic_command.downgrade(config, REVISION_0012)
    assert expected.isdisjoint(inspect(engine).get_table_names())
    alembic_command.upgrade(config, REVISION_0013)
    assert expected <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION_0013
