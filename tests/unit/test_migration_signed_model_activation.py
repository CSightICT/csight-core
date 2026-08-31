"""Offline contracts for signed model release migration 0028."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0027_analysis_text_erasure"
REVISION = "20260830_0028_signed_model_activation"
CURRENT_HEAD = "20260831_0036_policy_query_search_events_v2"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_signed_model_activation_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [CURRENT_HEAD]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_is_append_only_tenant_scoped_and_least_privilege() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "CREATE TABLE llm_release_manifests" in sql
    assert "CREATE TABLE llm_model_activation_events" in sql
    assert "CREATE FUNCTION csight_reject_model_release_mutation" in sql
    assert "BEFORE UPDATE OR DELETE ON llm_release_manifests" in sql
    assert "BEFORE UPDATE OR DELETE ON llm_model_activation_events" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "GRANT SELECT ON llm_model_activation_events TO csight_worker_role" in sql
    assert "GRANT SELECT, INSERT ON llm_release_manifests TO csight_api_role" in sql
    assert "csight_dispatcher_role" not in sql
