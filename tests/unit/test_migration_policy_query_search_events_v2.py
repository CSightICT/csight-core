"""Offline contract for the split query-build and policy-search runtime."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260831_0035_query_grounding_model_route_snapshot"
REVISION = "20260831_0036_policy_query_search_events_v2"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_policy_query_search_event_migration_is_the_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)

    assert scripts.get_heads() == ["20260910_0038_fixture_evidence_repair"]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_adds_event_type_and_search_queued_state() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "policy_retrieval_outbox_events ADD COLUMN event_type VARCHAR(128)" in sql
    assert "policy_query_build.requested.v2" in sql
    assert "policy_search.requested.v2" in sql
    assert "SEARCH_QUEUED" in sql
