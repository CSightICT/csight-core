"""Static migration contract for PRIMARY/SHADOW execution boundaries."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.unit

REVISION = "20260829_0019_analysis_execution_modes"
PREVIOUS = "20260829_0018_oidc_sessions"
MIGRATION = Path("alembic/versions/20260829_0019_analysis_execution_modes.py")


def test_analysis_execution_mode_migration_is_linear_and_fail_closed() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", "alembic")
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(REVISION)

    assert revision is not None
    assert revision.down_revision == PREVIOUS
    assert scripts.get_heads() == ["20260831_0034_analysis_model_route_snapshot"]

    source = MIGRATION.read_text(encoding="utf-8")
    assert "execution_mode IN ('PRIMARY','SHADOW')" in source
    assert "ix_analysis_runs_admission_nonterminal" in source
    assert "csight_analysis_execution_mode_immutable" in source
    assert "ck_shadow_analysis_no_downstream" in source
    for table_name in (
        "policy_evaluation_runs",
        "human_review_tasks",
        "human_review_decisions",
        "case_resolutions",
        "external_action_intents",
        "case_resolution_events",
        "external_action_simulation_request_events",
    ):
        assert table_name in source
