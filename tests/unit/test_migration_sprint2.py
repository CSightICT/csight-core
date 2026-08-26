"""Offline contract tests for the Sprint 2 Analysis/LLM Alembic revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit

SPRINT_1_REVISION = "20260826_0002"
SPRINT_2_REVISION = "20260826_0003"
SPRINT_2_TABLES = (
    "analysis_runs",
    "analysis_stage_runs",
    "analysis_stage_attempts",
    "llm_extraction_results",
    "analysis_request_idempotency_records",
    "outbox_events",
)


def _offline_config(output: StringIO) -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_sprint_2_revision_is_followed_by_the_sprint_3_revision() -> None:
    config = _offline_config(StringIO())
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(SPRINT_2_REVISION)

    assert scripts.get_current_head() == "20260826_0004"
    assert revision is not None
    assert revision.down_revision == SPRINT_1_REVISION


def test_sprint_2_upgrade_creates_exact_new_tables_and_safety_contracts() -> None:
    output = StringIO()
    command.upgrade(
        _offline_config(output),
        f"{SPRINT_1_REVISION}:{SPRINT_2_REVISION}",
        sql=True,
    )
    migration_sql = output.getvalue()

    assert (
        tuple(
            table_name
            for table_name in SPRINT_2_TABLES
            if f"CREATE TABLE {table_name} (" in migration_sql
        )
        == SPRINT_2_TABLES
    )
    assert "ALTER TABLE idempotency_records" not in migration_sql
    assert "CREATE TYPE" not in migration_sql.upper()
    assert "TIMESTAMP WITH TIME ZONE" in migration_sql
    assert "fk_analysis_runs_tenant_id_case_id_cases" in migration_sql
    assert "fk_analysis_stage_runs_tenant_id_analysis_run_id_analysis_runs" in migration_sql
    assert "fk_llm_results_tenant_run_stage_type_stage_runs" in migration_sql
    assert "stage_type = 'TEXT_EXTRACTION'" in migration_sql
    assert "uq_llm_extraction_results_tenant_analysis_run" in migration_sql
    assert "uq_llm_extraction_results_tenant_stage_run" in migration_sql
    assert "fk_analysis_request_idempotency_tenant_run_analysis_runs" in migration_sql
    assert "DEFERRABLE INITIALLY DEFERRED" in migration_sql
    assert "payload_allowed_keys" in migration_sql
    assert "customer_message" not in migration_sql
    assert "WHERE status = 'PENDING'" in migration_sql
    assert "WHERE status = 'PROCESSING'" in migration_sql
    assert "WHERE status = 'RUNNING'" in migration_sql
    assert "WHERE status = 'RETRY_WAITING'" in migration_sql


def test_sprint_2_downgrade_drops_only_new_tables_in_dependency_order() -> None:
    output = StringIO()
    command.downgrade(
        _offline_config(output),
        f"{SPRINT_2_REVISION}:{SPRINT_1_REVISION}",
        sql=True,
    )
    migration_sql = output.getvalue()

    expected_order = (
        "outbox_events",
        "analysis_request_idempotency_records",
        "llm_extraction_results",
        "analysis_stage_attempts",
        "analysis_stage_runs",
        "analysis_runs",
    )
    positions = [migration_sql.index(f"DROP TABLE {table_name}") for table_name in expected_order]
    assert positions == sorted(positions)
    assert "DROP TABLE idempotency_records" not in migration_sql
    assert "DROP TABLE cases" not in migration_sql
    assert "DROP EXTENSION" not in migration_sql.upper()
