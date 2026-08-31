"""Pin an optional immutable model route on each analysis stage.

Revision ID: 20260831_0034_analysis_model_route_snapshot
Revises: 20260831_0033_model_route_plans
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0034_analysis_model_route_snapshot"
down_revision: str | None = "20260831_0033_model_route_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_stage_runs",
        sa.Column("model_route_plan_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_analysis_stage_runs_tenant_route_plan",
        "analysis_stage_runs",
        "llm_model_route_plans",
        ["tenant_id", "model_route_plan_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_analysis_stage_runs_tenant_model_route_plan",
        "analysis_stage_runs",
        ["tenant_id", "model_route_plan_id"],
        unique=False,
        postgresql_where=sa.text("model_route_plan_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_stage_runs_tenant_model_route_plan",
        table_name="analysis_stage_runs",
    )
    op.drop_constraint(
        "fk_analysis_stage_runs_tenant_route_plan",
        "analysis_stage_runs",
        type_="foreignkey",
    )
    op.drop_column("analysis_stage_runs", "model_route_plan_id")
