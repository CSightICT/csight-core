"""Static contract for intake ownership and direct-object RLS."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "20260830_0026_case_assignment_ownership"


def test_case_assignment_revision_is_linear_audited_and_fail_closed() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_current_head() == "20260831_0036_policy_query_search_events_v2"
    script = scripts.get_revision(REVISION)
    assert script is not None
    assert script.down_revision == "20260830_0025_waiting_owner_and_similarity_contract"

    source = Path(script.path).read_text(encoding="utf-8")
    assert "case_assignment_actions" in source
    assert "resulting_version = expected_version + 1" in source
    assert "Case assignment actions are append-only" in source
    assert "CASE_ASSIGNMENT_INHERITANCE" in source
    assert "AS RESTRICTIVE FOR SELECT TO csight_api_role" in source
    assert "csight_can_access_case" in source
    assert "current_setting('app.actor_id', true)" in source
