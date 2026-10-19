"""Offline contracts for simulated communication and tenant data assets."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260827_0015_vision_image_assessment"
REVISION = "20260828_0016_communication_learning_assets"
CURRENT_HEAD = "20260910_0038_fixture_evidence_repair"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_communication_learning_asset_revision_is_single_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)
    assert scripts.get_heads() == [CURRENT_HEAD]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_is_additive_and_forbids_claimed_delivery() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE customer_communication_simulations" in sql
    assert "CREATE TABLE case_learning_assets" in sql
    assert "SIMULATED_NOT_SENT" in sql
    assert "side_effects_performed = false" in sql
    assert "raw_customer_message" not in sql


def test_downgrade_removes_only_added_asset_tables() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()
    assert "DROP TABLE case_learning_assets" in sql
    assert "DROP TABLE customer_communication_simulations" in sql
    assert "DROP TABLE review_reports" not in sql
