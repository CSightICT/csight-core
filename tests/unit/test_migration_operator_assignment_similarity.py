"""Static contract for the operator assignment and policy similarity revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.unit
REVISION = "20260830_0023_operator_assignment_similarity"


def test_operator_assignment_similarity_revision_is_linear_and_fail_closed() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", "alembic")
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(REVISION)

    assert revision is not None
    assert revision.down_revision == "20260829_0022_privacy_lifecycle"
    assert scripts.get_heads() == ["20260831_0034_analysis_model_route_snapshot"]

    source = Path(revision.path).read_text()
    assert "'ASSIGNED','REASSIGNED'" in source
    assert "policy_retrieval_similarity_evidence" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "REVOKE UPDATE, DELETE" in source
