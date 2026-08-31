"""Static contract for the additive schema-drift repair revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0023_operator_assignment_similarity"
REVISION = "20260830_0024_schema_drift_repair"


def test_schema_drift_repair_revision_is_linear_and_fail_closed() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", "alembic")
    scripts = ScriptDirectory.from_config(config)
    migration = scripts.get_revision(REVISION)

    assert migration is not None
    assert migration.down_revision == PREVIOUS
    assert scripts.get_heads() == ["20260831_0036_policy_query_search_events_v2"]

    source = Path(migration.path).read_text()
    assert "_CHECK_CONSTRAINT_RENAMES" in source
    assert "schema drift repair could not find" in source
    assert "uq_case_evidence_tenant_case_idempotency_sha256" in source
    assert "DROP CONSTRAINT uq_case_evidence_tenant_case_idempotency_sha256" not in source


def test_similarity_projection_declares_the_migration_owned_index() -> None:
    source = Path("app/adapters/persistence/models.py").read_text()

    assert '"ix_policy_retrieval_similarity_run_group"' in source
