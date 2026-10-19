"""Offline contracts for the service-pilot data lifecycle expansion."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260828_0016_communication_learning_assets"
REVISION = "20260829_0017_service_pilot_foundation"
HEAD = "20260910_0038_fixture_evidence_repair"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_service_pilot_revision_is_single_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [HEAD]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_is_additive_and_creates_lifecycle_boundaries() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "CREATE TABLE case_sensitive_payloads" in sql
    assert "CREATE TABLE data_lifecycle_events" in sql
    assert "ADD COLUMN idempotency_key" in sql
    assert "uq_case_evidence_tenant_case_idempotency_key" in sql
    assert "DROP COLUMN customer_message" not in sql
    assert "DROP TABLE cases" not in sql


def test_downgrade_removes_only_the_added_foundations() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "DROP TABLE data_lifecycle_events" in sql
    assert "DROP TABLE case_sensitive_payloads" in sql
    assert "DROP COLUMN idempotency_key" in sql
    assert "DROP TABLE cases" not in sql
