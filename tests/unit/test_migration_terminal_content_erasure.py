"""Offline contracts for migration 0029 terminal-content erasure."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0028_signed_model_activation"
REVISION = "20260830_0029_terminal_content_erasure"
CURRENT_HEAD = "20260910_0038_fixture_evidence_repair"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_terminal_content_erasure_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [CURRENT_HEAD]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_adds_projection_and_deferred_guards() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "ADD COLUMN terminal_content_purged_at" in sql
    assert "CREATE FUNCTION csight_assert_terminal_content_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_payload_terminal_content_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_decision_terminal_content_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_report_terminal_content_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_communication_terminal_content_erasure" in sql
    assert "customer-derived terminal content remains" in sql
    assert "DROP TABLE" not in sql


def test_downgrade_refuses_to_claim_redacted_terminal_content_can_be_restored() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "terminal content erasure downgrade blocked" in sql
    assert "DROP COLUMN terminal_content_purged_at" in sql
