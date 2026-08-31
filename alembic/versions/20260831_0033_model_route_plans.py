"""Generalize signed LLM tasks and add immutable model route plans.

Revision ID: 20260831_0033_model_route_plans
Revises: 20260831_0032_signed_case_intake
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0033_model_route_plans"
down_revision: str | None = "20260831_0032_signed_case_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASKS_SQL = (
    "'PRODUCT_DEFECT_TEXT_EXTRACTION_V2','POLICY_QUERY_BUILDER_V1','GROUNDED_POLICY_EXPLANATION_V1'"
)
_TENANT_EXPRESSION = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_TABLE = "llm_model_route_plans"


def upgrade() -> None:
    _expand_release_tasks()
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("model_activation_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.String(128), nullable=False),
        sa.Column("previous_route_plan_id", sa.Uuid(), nullable=True),
        sa.Column(
            "automatic_cross_model_fallback",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("activated_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "schema_version = 'model_route_plan/1.0.0'",
            name=op.f("ck_llm_model_route_plans_schema_version_supported"),
        ),
        sa.CheckConstraint(
            f"task IN ({_TASKS_SQL})",
            name=op.f("ck_llm_model_route_plans_task_supported"),
        ),
        sa.CheckConstraint(
            "execution_mode IN ('PRIMARY', 'SHADOW')",
            name=op.f("ck_llm_model_route_plans_execution_mode_supported"),
        ),
        sa.CheckConstraint(
            "deployment_id ~ '^[a-z0-9][a-z0-9._-]{2,127}$'",
            name=op.f("ck_llm_model_route_plans_deployment_id_valid"),
        ),
        sa.CheckConstraint(
            "automatic_cross_model_fallback = false",
            name=op.f("ck_llm_model_route_plans_automatic_fallback_disabled"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_llm_model_route_plans_request_hash_valid"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0",
            name=op.f("ck_llm_model_route_plans_reason_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_llm_model_route_plans_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            "previous_route_plan_id IS NULL OR previous_route_plan_id <> id",
            name=op.f("ck_llm_model_route_plans_previous_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_llm_model_route_plans_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task", "execution_mode", "model_activation_id"],
            [
                "llm_model_activation_events.tenant_id",
                "llm_model_activation_events.task",
                "llm_model_activation_events.execution_mode",
                "llm_model_activation_events.id",
            ],
            name="fk_llm_model_route_plans_activation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task", "execution_mode", "previous_route_plan_id"],
            [
                "llm_model_route_plans.tenant_id",
                "llm_model_route_plans.task",
                "llm_model_route_plans.execution_mode",
                "llm_model_route_plans.id",
            ],
            name="fk_llm_model_route_plans_previous",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "activated_by"],
            ["users.tenant_id", "users.id"],
            name="fk_llm_model_route_plans_activated_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_model_route_plans")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_llm_model_route_plans_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "id",
            name="uq_llm_model_route_plans_tenant_mode_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "previous_route_plan_id",
            name="uq_llm_model_route_plans_previous",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "task",
            "execution_mode",
            "idempotency_key",
            name="uq_llm_model_route_plans_idempotency",
        ),
    )
    op.create_index(
        "ix_llm_model_route_plans_active",
        _TABLE,
        ["tenant_id", "task", "execution_mode", sa.text("activated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "uq_llm_model_route_plans_root",
        _TABLE,
        ["tenant_id", "task", "execution_mode"],
        unique=True,
        postgresql_where=sa.text("previous_route_plan_id IS NULL"),
    )
    _install_append_only_rls()


def _expand_release_tasks() -> None:
    op.drop_constraint(
        op.f("ck_llm_release_manifests_task_supported"),
        "llm_release_manifests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_llm_release_manifests_task_supported"),
        "llm_release_manifests",
        f"task IN ({_TASKS_SQL})",
    )
    op.drop_constraint(
        op.f("ck_llm_model_activation_events_task_supported"),
        "llm_model_activation_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_llm_model_activation_events_task_supported"),
        "llm_model_activation_events",
        f"task IN ({_TASKS_SQL})",
    )
    op.drop_constraint(
        "uq_llm_release_manifests_package_version",
        "llm_release_manifests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_llm_release_manifests_package_version",
        "llm_release_manifests",
        ["tenant_id", "task", "package_name", "package_version"],
    )


def _install_append_only_rls() -> None:
    op.execute(
        f"""
        CREATE TRIGGER trg_{_TABLE}_append_only
        BEFORE UPDATE OR DELETE ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION csight_reject_model_release_mutation()
        """
    )
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO csight_api_role")
    op.execute(f"GRANT SELECT ON {_TABLE} TO csight_worker_role")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY csight_api_tenant_scope ON {_TABLE}
        FOR ALL TO csight_api_role
        USING ({_TENANT_EXPRESSION})
        WITH CHECK ({_TENANT_EXPRESSION})
        """
    )
    op.execute(
        f"""
        CREATE POLICY csight_worker_tenant_select ON {_TABLE}
        FOR SELECT TO csight_worker_role
        USING ({_TENANT_EXPRESSION})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS csight_worker_tenant_select ON {_TABLE}")
    op.execute(f"DROP POLICY IF EXISTS csight_api_tenant_scope ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL PRIVILEGES ON {_TABLE} FROM csight_worker_role")
    op.execute(f"REVOKE ALL PRIVILEGES ON {_TABLE} FROM csight_api_role")
    op.execute(f"DROP TRIGGER IF EXISTS trg_{_TABLE}_append_only ON {_TABLE}")
    op.drop_index("uq_llm_model_route_plans_root", table_name=_TABLE)
    op.drop_index("ix_llm_model_route_plans_active", table_name=_TABLE)
    op.drop_table(_TABLE)
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM llm_release_manifests
             WHERE task <> 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'
          ) OR EXISTS (
            SELECT 1 FROM llm_model_activation_events
             WHERE task <> 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'
          ) THEN
            RAISE EXCEPTION 'cannot downgrade while generalized LLM task records exist';
          END IF;
        END;
        $$
        """
    )
    op.drop_constraint(
        "uq_llm_release_manifests_package_version",
        "llm_release_manifests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_llm_release_manifests_package_version",
        "llm_release_manifests",
        ["tenant_id", "package_name", "package_version"],
    )
    op.drop_constraint(
        op.f("ck_llm_model_activation_events_task_supported"),
        "llm_model_activation_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_llm_model_activation_events_task_supported"),
        "llm_model_activation_events",
        "task = 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'",
    )
    op.drop_constraint(
        op.f("ck_llm_release_manifests_task_supported"),
        "llm_release_manifests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_llm_release_manifests_task_supported"),
        "llm_release_manifests",
        "task = 'PRODUCT_DEFECT_TEXT_EXTRACTION_V2'",
    )
