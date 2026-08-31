"""Offline migration contracts for the fail-closed privacy lifecycle slice."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260829_0021_failure_recovery"
REVISION = "20260829_0022_privacy_lifecycle"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_privacy_lifecycle_revision_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == ["20260831_0034_analysis_model_route_snapshot"]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_adds_gates_events_and_deferred_contract_without_dropping_legacy() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "privacy lifecycle preflight failed: missing sensitive payload rows" in sql
    assert "privacy lifecycle preflight failed: dual-write parity mismatch" in sql
    assert "ADD COLUMN legacy_redacted_at" in sql
    assert "ADD COLUMN operation_key" in sql
    assert "EVIDENCE_PURGE_REQUESTED" in sql
    assert (
        "REVOKE UPDATE, DELETE ON data_lifecycle_events "
        "FROM csight_api_role, csight_worker_role" in sql
    )
    assert "CREATE CONSTRAINT TRIGGER trg_cases_sensitive_payload_contract" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_sensitive_payload_contract" in sql
    assert "IF TG_OP = 'DELETE'" in sql
    assert "DROP COLUMN customer_message" not in sql
    assert "DROP TABLE cases" not in sql


def test_downgrade_is_blocked_after_irreversible_purge() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "privacy lifecycle downgrade blocked: purged payloads cannot be restored" in sql
    assert "DROP COLUMN operation_key" in sql
    assert "DROP COLUMN legacy_redacted_at" in sql
    assert "DROP COLUMN customer_message" not in sql
