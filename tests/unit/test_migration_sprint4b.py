"""Offline contract checks for the append-only Sprint 4B migration."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit


def _offline_config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost/placeholder",
    )
    return config


def test_migration_0006_is_head_and_creates_policy_retrieval_tables() -> None:
    scripts = ScriptDirectory.from_config(_offline_config(StringIO()))
    revision = scripts.get_revision("20260826_0006")
    assert scripts.get_heads() == ["20260826_0006"]
    assert revision is not None and revision.down_revision == "20260826_0005"

    output = StringIO()
    command.upgrade(_offline_config(output), "20260826_0005:20260826_0006", sql=True)
    sql = output.getvalue()
    for table in (
        "policy_ingestion_runs",
        "policy_documents",
        "policy_clauses",
        "policy_embedding_profiles",
        "policy_clause_embeddings",
        "policy_index_versions",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "vector not null" in sql.lower()
    assert "vector(1024)" not in sql.lower()
    assert "status = 'ACTIVE'" in sql
    assert "DROP TABLE llm_extraction_results_v2" not in sql


def test_migration_0006_downgrade_removes_only_policy_retrieval_tables() -> None:
    output = StringIO()
    command.downgrade(_offline_config(output), "20260826_0006:20260826_0005", sql=True)
    sql = output.getvalue()
    assert "DROP TABLE policy_index_versions" in sql
    assert "DROP TABLE policy_ingestion_runs" in sql
    assert "DROP TABLE llm_extraction_results_v2" not in sql
    assert "DROP TABLE analysis_runs" not in sql
