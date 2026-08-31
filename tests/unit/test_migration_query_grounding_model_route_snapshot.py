"""Offline contract for nullable query-builder and grounding route snapshots."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import ForeignKeyConstraint

from alembic import command
from app.adapters.persistence.base import Base
from app.adapters.persistence.model_registry import PERSISTENCE_MODELS

pytestmark = pytest.mark.unit
PREVIOUS = "20260831_0034_analysis_model_route_snapshot"
REVISION = "20260831_0035_query_grounding_model_route_snapshot"
_LOADED_MODELS = PERSISTENCE_MODELS


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_route_snapshot_migration_is_the_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [REVISION]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_adds_mode_nullable_route_and_tenant_fk_to_both_runs() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    for table_name in ("policy_retrieval_runs", "grounded_explanation_runs"):
        assert f"ALTER TABLE {table_name} ADD COLUMN execution_mode VARCHAR(16)" in sql
        assert f"fk_{table_name}_tenant_route_plan" in sql
        assert f"ix_{table_name}_tenant_model_route_plan" in sql
    assert sql.count("ADD COLUMN model_route_plan_id UUID") == 2
    assert sql.count("model_route_plan_id UUID NOT NULL") == 0
    assert sql.count("FOREIGN KEY(tenant_id, model_route_plan_id)") == 2
    assert sql.count("WHERE model_route_plan_id IS NOT NULL") == 2


@pytest.mark.parametrize(
    "table_name,fk_name",
    (
        ("policy_retrieval_runs", "fk_policy_retrieval_runs_tenant_route_plan"),
        (
            "grounded_explanation_runs",
            "fk_grounded_explanation_runs_tenant_route_plan",
        ),
    ),
)
def test_orm_metadata_maps_nullable_tenant_scoped_route_snapshots(
    table_name: str,
    fk_name: str,
) -> None:
    table = Base.metadata.tables[table_name]
    assert table.c.execution_mode.nullable is False
    assert table.c.model_route_plan_id.nullable is True
    assert table.c.route_enforcement_contract_version.nullable is True
    route_fk = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name == fk_name
    )
    assert tuple(column.name for column in route_fk.columns) == (
        "tenant_id",
        "model_route_plan_id",
    )
    assert tuple(element.target_fullname for element in route_fk.elements) == (
        "llm_model_route_plans.tenant_id",
        "llm_model_route_plans.id",
    )
