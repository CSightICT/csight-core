"""Offline contracts for migration 0031 OIDC back-channel logout."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0030_case_source_scope"
REVISION = "20260830_0031_oidc_backchannel_logout"
CURRENT_HEAD = "20260910_0038_fixture_evidence_repair"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_oidc_backchannel_logout_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [CURRENT_HEAD]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_adds_hashed_provider_capabilities_receipts_and_rls_policy() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "ADD COLUMN provider_session_id" in sql
    assert "ADD COLUMN provider_subject_hash" in sql
    assert "CREATE TABLE oidc_logout_events" in sql
    assert "uq_oidc_logout_events_token_jti_hash" in sql
    assert "csight_oidc_provider_logout_update" in sql
    assert "csight_oidc_provider_logout_select" in sql
    assert "app.oidc_logout_subject_hash" in sql
    assert "app.oidc_logout_session_hash" in sql
    assert "GRANT INSERT ON oidc_logout_events TO csight_api_role" in sql
    assert "GRANT SELECT" not in sql
