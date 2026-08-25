"""Offline smoke test for the PostgreSQL-only Sprint 0 baseline."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.unit


def test_baseline_upgrade_enables_only_vector_extension() -> None:
    project_root = Path(__file__).resolve().parents[2]
    output = StringIO()
    config = Config(str(project_root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )

    command.upgrade(config, "head", sql=True)

    migration_sql = output.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration_sql
    created_tables = [
        line.strip() for line in migration_sql.splitlines() if line.startswith("CREATE TABLE")
    ]
    assert created_tables == ["CREATE TABLE alembic_version ("]
