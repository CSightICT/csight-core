"""Offline contract tests for the Sprint 3 Vision Alembic revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit

SPRINT_2_REVISION = "20260826_0003"
SPRINT_3_REVISION = "20260826_0004"
SPRINT_3_TABLES = (
    "analysis_run_evidence",
    "vision_analysis_results",
    "vision_detections",
)


def _offline_config(output: StringIO) -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_sprint_3_is_the_single_head_and_follows_sprint_2() -> None:
    scripts = ScriptDirectory.from_config(_offline_config(StringIO()))
    revision = scripts.get_revision(SPRINT_3_REVISION)

    assert scripts.get_heads() == ["20260910_0038_fixture_evidence_repair"]
    assert revision is not None
    assert revision.down_revision == SPRINT_2_REVISION


def test_sprint_3_upgrade_creates_snapshot_and_append_only_vision_tables() -> None:
    output = StringIO()
    command.upgrade(
        _offline_config(output),
        f"{SPRINT_2_REVISION}:{SPRINT_3_REVISION}",
        sql=True,
    )
    migration_sql = output.getvalue()

    for table_name in SPRINT_3_TABLES:
        assert f"CREATE TABLE {table_name} (" in migration_sql
    assert "product_defect_multimodal_analysis" in migration_sql
    assert "PARTIAL_SUCCESS" in migration_sql
    assert "fk_analysis_run_evidence_tenant_evidence_case_evidence" in migration_sql
    assert "fk_vision_results_tenant_run_stage_type_stage_runs" in migration_sql
    assert "uq_vision_results_tenant_run_evidence" in migration_sql
    assert "coordinate_system = 'normalized_xyxy'" in migration_sql
    assert "confidence BETWEEN 0 AND 1" in migration_sql
    assert "ON DELETE RESTRICT" in migration_sql
    assert "DROP TABLE cases" not in migration_sql


def test_sprint_3_downgrade_drops_only_new_tables_in_dependency_order() -> None:
    output = StringIO()
    command.downgrade(
        _offline_config(output),
        f"{SPRINT_3_REVISION}:{SPRINT_2_REVISION}",
        sql=True,
    )
    migration_sql = output.getvalue()

    expected_order = (
        "vision_detections",
        "vision_analysis_results",
        "analysis_run_evidence",
    )
    positions = [migration_sql.index(f"DROP TABLE {name}") for name in expected_order]
    assert positions == sorted(positions)
    assert (
        "product_defect_multimodal_analysis"
        not in migration_sql.split("DROP TABLE analysis_run_evidence", maxsplit=1)[1]
    )
    assert "DROP TABLE analysis_runs" not in migration_sql
    assert "DROP TABLE case_evidence" not in migration_sql
