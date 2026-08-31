"""Disposable PostgreSQL proof for schema-drift repair revision 0024."""

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

from alembic import command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260830_0023_operator_assignment_similarity"
REVISION = "20260830_0024_schema_drift_repair"
HEAD = "head"

EXPECTED_CHECKS = {
    "operational_failures": {
        "ck_operational_failures_code_safe",
        "ck_operational_failures_correlation_nonempty",
        "ck_operational_failures_kind_allowed",
        "ck_operational_failures_pipeline_allowed",
        "ck_operational_failures_replayable_dispatch_only",
        "ck_operational_failures_source_allowed",
    },
    "operational_failure_recovery_runs": {
        "ck_operational_failure_recovery_runs_hash_valid",
        "ck_operational_failure_recovery_runs_key_nonempty",
    },
    "operational_failure_recovery_events": {
        "ck_operational_failure_recovery_events_topic_allowed",
        "ck_operational_failure_recovery_events_payload_allowlist",
        "ck_operational_failure_recovery_events_payload_identifiers",
        "ck_operational_failure_recovery_events_attempts_nonnegative",
        "ck_operational_failure_recovery_events_state_consistent",
        "ck_operational_failure_recovery_events_status_allowed",
    },
    "operational_failure_resolutions": {
        "ck_operational_failure_resolutions_action_allowed",
        "ck_operational_failure_resolutions_reason_allowed",
        "ck_operational_failure_resolutions_action_consistent",
        "ck_operational_failure_resolutions_hashes_valid",
    },
}


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0024")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0024 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0024 integration tests require PostgreSQL")

    database_name = f"csight_migration_0024_{uuid4().hex[:16]}"
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


def _assert_repaired(engine: Engine) -> None:
    inspector = inspect(engine)
    for table_name, expected in EXPECTED_CHECKS.items():
        actual = {
            str(item["name"])
            for item in inspector.get_check_constraints(table_name)
            if item["name"] is not None
        }
        assert expected <= actual
        assert not any("_ck_" in name for name in actual)

    evidence_uniques = {item["name"] for item in inspector.get_unique_constraints("case_evidence")}
    assert "uq_case_evidence_tenant_case_idempotency_sha256" in evidence_uniques
    similarity_indexes = {
        item["name"] for item in inspector.get_indexes("policy_retrieval_similarity_evidence")
    }
    assert "ix_policy_retrieval_similarity_run_group" in similarity_indexes


def test_blank_and_preexisting_drift_paths_converge(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine

    command.upgrade(config, HEAD)
    _assert_repaired(engine)
    command.check(config)

    command.downgrade(config, PREVIOUS)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE case_evidence DROP CONSTRAINT "
                "uq_case_evidence_tenant_case_idempotency_sha256"
            )
        )

    command.upgrade(config, HEAD)
    _assert_repaired(engine)
    command.check(config)

    command.upgrade(config, HEAD)
    _assert_repaired(engine)
