"""Static migration checks for waiting-review ownership continuity."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "20260830_0025_waiting_owner_and_similarity_contract"


def test_waiting_owner_migration_is_head_and_fail_closed() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_current_head() == "20260910_0038_fixture_evidence_repair"
    script = scripts.get_revision(REVISION)
    assert script is not None
    assert script.down_revision == "20260830_0024_schema_drift_repair"

    source = Path(script.path).read_text(encoding="utf-8")
    assert "WAITING_OWNER_RECOVERY" in source
    assert "waiting review task has no recoverable assignee" in source
    assert "status IN ('CLAIMED','WAITING_FOR_EVIDENCE')" in source
    assert "current_assignee_id IS NOT NULL" in source
