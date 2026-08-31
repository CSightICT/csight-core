"""Offline migration contracts for generalized LLM task routing."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260831_0032_signed_case_intake"
REVISION = "20260831_0033_model_route_plans"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_model_route_plan_revision_is_the_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == ["20260831_0035_query_grounding_model_route_snapshot"]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_generalizes_tasks_and_installs_fixed_append_only_routes() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    for task in (
        "PRODUCT_DEFECT_TEXT_EXTRACTION_V2",
        "POLICY_QUERY_BUILDER_V1",
        "GROUNDED_POLICY_EXPLANATION_V1",
    ):
        assert task in sql
    assert "UNIQUE (tenant_id, task, package_name, package_version)" in sql
    assert "CREATE TABLE llm_model_route_plans" in sql
    assert "automatic_cross_model_fallback = false" in sql
    assert "BEFORE UPDATE OR DELETE ON llm_model_route_plans" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "GRANT SELECT, INSERT ON llm_model_route_plans TO csight_api_role" in sql
    assert "GRANT SELECT ON llm_model_route_plans TO csight_worker_role" in sql
    assert "csight_dispatcher_role" not in sql
