"""Offline contracts for migration 0030 Case source scope."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0029_terminal_content_erasure"
REVISION = "20260830_0030_case_source_scope"
CURRENT_HEAD = "20260831_0035_query_grounding_model_route_snapshot"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_case_source_scope_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)
    assert scripts.get_heads() == [CURRENT_HEAD]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_backfills_and_makes_source_scope_immutable() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "ADD COLUMN source_scope" in sql
    assert "SYNTHETIC_DEMO" in sql
    assert "trg_cases_source_scope_immutable" in sql
    assert "PILOT_LIVE" in sql
