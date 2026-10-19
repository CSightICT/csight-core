"""Offline contract for nullable, tenant-scoped analysis route snapshots."""

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
PREVIOUS = "20260831_0033_model_route_plans"
REVISION = "20260831_0034_analysis_model_route_snapshot"
_LOADED_MODELS = PERSISTENCE_MODELS


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_analysis_model_route_snapshot_precedes_query_and_grounding_snapshots() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)

    assert scripts.get_heads() == ["20260910_0038_fixture_evidence_repair"]
    assert migration is not None
    assert migration.down_revision == PREVIOUS


def test_upgrade_adds_nullable_tenant_fk_and_partial_lookup_index() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "ADD COLUMN model_route_plan_id UUID" in sql
    assert "model_route_plan_id UUID NOT NULL" not in sql
    assert "fk_analysis_stage_runs_tenant_route_plan" in sql
    assert "FOREIGN KEY(tenant_id, model_route_plan_id)" in sql
    assert "REFERENCES llm_model_route_plans (tenant_id, id)" in sql
    assert "ix_analysis_stage_runs_tenant_model_route_plan" in sql
    assert "WHERE model_route_plan_id IS NOT NULL" in sql


def test_orm_metadata_maps_the_nullable_tenant_scoped_route_snapshot() -> None:
    table = Base.metadata.tables["analysis_stage_runs"]
    assert table.c.model_route_plan_id.nullable is True
    route_fk = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_analysis_stage_runs_tenant_route_plan"
    )
    assert tuple(column.name for column in route_fk.columns) == (
        "tenant_id",
        "model_route_plan_id",
    )
    assert tuple(element.target_fullname for element in route_fk.elements) == (
        "llm_model_route_plans.tenant_id",
        "llm_model_route_plans.id",
    )
    index = next(
        item
        for item in table.indexes
        if item.name == "ix_analysis_stage_runs_tenant_model_route_plan"
    )
    assert str(index.dialect_options["postgresql"]["where"]) == ("model_route_plan_id IS NOT NULL")
