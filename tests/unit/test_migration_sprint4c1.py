"""Offline contract checks for the Sprint 4C-1 profile migration."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://placeholder:placeholder@localhost/placeholder"
    )
    return config


def test_migration_0007_is_head_and_adds_only_reranker_profiles() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision("20260826_0007")
    assert scripts.get_heads() == ["20260831_0036_policy_query_search_events_v2"]
    assert revision is not None and revision.down_revision == "20260826_0006"
    output = StringIO()
    command.upgrade(_config(output), "20260826_0006:20260826_0007", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE policy_reranker_profiles" in sql
    assert "CREATE TABLE policy_retrieval_execution_profiles" in sql
    assert "DROP TABLE policy_index_versions" not in sql


def test_migration_0007_downgrade_preserves_sprint4b() -> None:
    output = StringIO()
    command.downgrade(_config(output), "20260826_0007:20260826_0006", sql=True)
    sql = output.getvalue()
    assert "DROP TABLE policy_retrieval_execution_profiles" in sql
    assert "DROP TABLE policy_reranker_profiles" in sql
    assert "DROP TABLE policy_index_versions" not in sql
