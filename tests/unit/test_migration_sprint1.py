"""Offline contract tests for the Sprint 1 Alembic revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit

BASELINE_REVISION = "20260825_0001"
SPRINT_1_REVISION = "20260826_0002"


def _offline_config(output: StringIO) -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_sprint_1_revision_follows_the_preserved_baseline() -> None:
    config = _offline_config(StringIO())
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(SPRINT_1_REVISION)

    assert revision is not None
    assert revision.down_revision == BASELINE_REVISION


def test_sprint_1_upgrade_creates_expected_postgresql_schema() -> None:
    output = StringIO()
    config = _offline_config(output)

    command.upgrade(config, f"{BASELINE_REVISION}:{SPRINT_1_REVISION}", sql=True)

    migration_sql = output.getvalue()
    for table_name in (
        "tenants",
        "users",
        "roles",
        "user_roles",
        "cases",
        "case_evidence",
        "case_status_history",
        "idempotency_records",
    ):
        assert f"CREATE TABLE {table_name} (" in migration_sql

    assert "CREATE TYPE" not in migration_sql.upper()
    assert "TIMESTAMP WITH TIME ZONE" in migration_sql
    assert "CONSTRAINT fk_cases_tenant_id_created_by_users" in migration_sql
    assert "CONSTRAINT fk_case_evidence_tenant_id_case_id_cases" in migration_sql
    assert "CONSTRAINT fk_case_status_history_tenant_id_actor_id_users" in migration_sql
    assert "CONSTRAINT fk_idempotency_records_tenant_id_resource_id_cases" in migration_sql
    assert "DEFERRABLE INITIALLY DEFERRED" in migration_sql
    assert "CONSTRAINT ck_cases_status_allowed" in migration_sql
    assert "CONSTRAINT ck_case_evidence_upload_status_allowed" in migration_sql
    assert "CONSTRAINT uq_idempotency_records_tenant_operation_key" in migration_sql
    assert "CREATE INDEX ix_cases_tenant_status_created_id" in migration_sql
    assert "CREATE INDEX ix_case_evidence_case_sha256" in migration_sql


def test_sprint_1_downgrade_drops_only_sprint_1_objects() -> None:
    output = StringIO()
    config = _offline_config(output)

    command.downgrade(config, f"{SPRINT_1_REVISION}:{BASELINE_REVISION}", sql=True)

    migration_sql = output.getvalue()
    assert "DROP TABLE idempotency_records" in migration_sql
    assert "DROP TABLE tenants" in migration_sql
    assert "DROP EXTENSION" not in migration_sql.upper()
