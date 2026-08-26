"""Offline migration-chain contract for Sprint 4C-2."""

from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_0008_is_single_head_and_follows_0007() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", str(Path("alembic")))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20260826_0008")

    assert scripts.get_heads() == ["20260826_0008"]
    assert revision is not None
    assert revision.down_revision == "20260826_0007"


def test_migration_0008_contains_run_query_hit_profile_and_outbox_tables() -> None:
    source = Path("alembic/versions/20260826_0008_policy_query_builder.py").read_text()
    for table in (
        "policy_query_builder_profiles",
        "policy_retrieval_runs",
        "policy_retrieval_run_queries",
        "policy_retrieval_run_hits",
        "policy_retrieval_outbox_events",
    ):
        assert f'"{table}"' in source
