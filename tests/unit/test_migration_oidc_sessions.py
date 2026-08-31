"""Offline Alembic contracts for OIDC login transactions and hashed sessions."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from app.adapters.persistence.model_registry import PERSISTENCE_MODELS

pytestmark = pytest.mark.unit

PREVIOUS = "20260829_0017_service_pilot_foundation"
REVISION = "20260829_0018_oidc_sessions"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_oidc_revision_is_linear_from_service_pilot_foundation() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert revision is not None
    assert revision.down_revision == PREVIOUS
    assert REVISION in {
        candidate.revision for candidate in scripts.walk_revisions(base="base", head="heads")
    }
    assert {"oidc_login_transactions", "oidc_sessions"}.issubset(
        {model.__tablename__ for model in PERSISTENCE_MODELS}
    )


def test_oidc_upgrade_contains_only_hashes_for_browser_session_and_csrf_secrets() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "CREATE TABLE oidc_login_transactions" in sql
    assert "CREATE TABLE oidc_sessions" in sql
    assert "session_id_hash" in sql
    assert "csrf_token_hash" in sql
    assert "state_hash" in sql
    assert "pkce_verifier" in sql
    assert "consumed_at" in sql
    assert '"session_id" VARCHAR' not in sql
    assert '"csrf_token" VARCHAR' not in sql
    assert "INTERVAL '8 hours'" in sql
    assert "INTERVAL '30 minutes'" in sql


def test_oidc_downgrade_removes_only_oidc_foundation_tables() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "DROP TABLE oidc_sessions" in sql
    assert "DROP TABLE oidc_login_transactions" in sql
    assert "DROP TABLE users" not in sql
    assert "DROP TABLE tenants" not in sql
