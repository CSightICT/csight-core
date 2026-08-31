"""Pin optional model routes on policy-query and grounding runs.

Revision ID: 20260831_0035_query_grounding_model_route_snapshot
Revises: 20260831_0034_analysis_model_route_snapshot
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0035_query_grounding_model_route_snapshot"
down_revision: str | None = "20260831_0034_analysis_model_route_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("policy_retrieval_runs", "grounded_explanation_runs")


def upgrade() -> None:
    for table_name in _TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "execution_mode",
                sa.String(length=16),
                nullable=False,
                server_default="PRIMARY",
            ),
        )
        op.add_column(
            table_name,
            sa.Column("model_route_plan_id", sa.Uuid(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column(
                "route_enforcement_contract_version",
                sa.String(length=64),
                nullable=True,
            ),
        )
        op.create_check_constraint(
            op.f(f"ck_{table_name}_execution_mode_allowed"),
            table_name,
            "execution_mode IN ('PRIMARY','SHADOW')",
        )
        op.create_check_constraint(
            op.f(f"ck_{table_name}_route_snapshot_consistent"),
            table_name,
            "(model_route_plan_id IS NULL) = (route_enforcement_contract_version IS NULL)",
        )
        op.create_foreign_key(
            f"fk_{table_name}_tenant_route_plan",
            table_name,
            "llm_model_route_plans",
            ["tenant_id", "model_route_plan_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            f"ix_{table_name}_tenant_model_route_plan",
            table_name,
            ["tenant_id", "model_route_plan_id"],
            unique=False,
            postgresql_where=sa.text("model_route_plan_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table_name in reversed(_TABLES):
        op.drop_index(
            f"ix_{table_name}_tenant_model_route_plan",
            table_name=table_name,
        )
        op.drop_constraint(
            f"fk_{table_name}_tenant_route_plan",
            table_name,
            type_="foreignkey",
        )
        op.drop_constraint(
            op.f(f"ck_{table_name}_route_snapshot_consistent"),
            table_name,
            type_="check",
        )
        op.drop_constraint(
            op.f(f"ck_{table_name}_execution_mode_allowed"),
            table_name,
            type_="check",
        )
        op.drop_column(table_name, "route_enforcement_contract_version")
        op.drop_column(table_name, "model_route_plan_id")
        op.drop_column(table_name, "execution_mode")
