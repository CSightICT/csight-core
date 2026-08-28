"""Offline migration-chain contract for Sprint 4C-3A."""

from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_0009_is_single_head_and_follows_0008() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", str(Path("alembic")))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20260827_0009")

    assert scripts.get_heads() == ["20260828_0016_communication_learning_assets"]
    assert revision is not None
    assert revision.down_revision == "20260826_0008"


def test_migration_0009_contains_citation_grounding_tables() -> None:
    source = Path("alembic/versions/20260827_0009_citation_grounding.py").read_text()
    for table in (
        "grounding_profiles",
        "policy_citation_packs",
        "policy_citation_pack_items",
        "grounded_explanation_runs",
        "grounded_explanation_results",
        "grounded_explanation_outbox_events",
    ):
        assert f'"{table}"' in source
