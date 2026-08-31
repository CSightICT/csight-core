"""Add intake-level Case assignment and reviewer ownership enforcement.

Revision ID: 20260830_0026_case_assignment_ownership
Revises: 20260830_0025_waiting_owner_and_similarity_contract
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0026_case_assignment_ownership"
down_revision: str | None = "20260830_0025_waiting_owner_and_similarity_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HUMAN_ASSIGNMENT_CHECK = "ck_human_review_assignments_type_allowed"
_NEW_TABLES = ("case_assignments", "case_assignment_actions")
_CASE_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("cases", "id"),
    ("case_assignments", "case_id"),
    ("case_assignment_actions", "case_id"),
    ("case_evidence", "case_id"),
    ("case_sensitive_payloads", "case_id"),
    ("case_status_history", "case_id"),
    ("analysis_runs", "case_id"),
    ("policy_retrieval_runs", "case_id"),
    ("grounded_explanation_runs", "case_id"),
    ("policy_evaluation_runs", "case_id"),
    ("human_review_tasks", "case_id"),
    ("case_resolutions", "case_id"),
    ("case_resolution_events", "case_id"),
    ("external_action_intents", "case_id"),
    ("review_reports", "case_id"),
    ("customer_communication_simulations", "case_id"),
    ("case_learning_assets", "case_id"),
)


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("current_assignee_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column(
            "assignment_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_foreign_key(
        "fk_cases_current_assignee",
        "cases",
        "users",
        ["tenant_id", "current_assignee_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_cases_assignment_version_nonnegative"),
        "cases",
        "assignment_version >= 0",
    )

    op.create_table(
        "case_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column("assignment_type", sa.String(32), nullable=False),
        sa.Column("rationale", sa.String(500), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_case_assignments_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_case_assignments_assignee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_by"],
            ["users.tenant_id", "users.id"],
            name="fk_case_assignments_assigner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assignment_type IN ('ADMIN_ASSIGNMENT','ADMIN_REASSIGNMENT','REVIEW_TASK_BACKFILL')",
            name=op.f("ck_case_assignments_type_allowed"),
        ),
        sa.CheckConstraint(
            "length(btrim(rationale)) BETWEEN 5 AND 500",
            name=op.f("ck_case_assignments_rationale_length"),
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= assigned_at",
            name=op.f("ck_case_assignments_released_after_assigned"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_assignments")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_assignments_tenant_id"),
    )
    op.create_index(
        "uq_case_assignments_current",
        "case_assignments",
        ["tenant_id", "case_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_case_assignments_assignee",
        "case_assignments",
        ["tenant_id", "assignee_id", "assigned_at"],
    )

    op.create_table(
        "case_assignment_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("from_assignee_id", sa.Uuid(), nullable=True),
        sa.Column("to_assignee_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("rationale", sa.String(500), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_case_assignment_actions_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_case_assignment_actions_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "to_assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_case_assignment_actions_to_assignee",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action_type IN ('ASSIGNED','REASSIGNED','BACKFILLED')",
            name=op.f("ck_case_assignment_actions_type_allowed"),
        ),
        sa.CheckConstraint(
            "resulting_version = expected_version + 1",
            name=op.f("ck_case_assignment_actions_version_step"),
        ),
        sa.CheckConstraint(
            "length(btrim(rationale)) BETWEEN 5 AND 500",
            name=op.f("ck_case_assignment_actions_rationale_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_assignment_actions")),
        sa.UniqueConstraint(
            "tenant_id",
            "case_id",
            "resulting_version",
            name="uq_case_assignment_actions_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_case_assignment_actions_tenant_id",
        ),
    )

    _expand_human_assignment_type()
    _backfill_from_review_ownership()
    op.create_check_constraint(
        op.f("ck_cases_assignment_projection_consistent"),
        "cases",
        "(assignment_version = 0 AND current_assignee_id IS NULL) OR "
        "(assignment_version > 0 AND current_assignee_id IS NOT NULL)",
    )
    _create_append_only_guard()
    _enable_rls_and_case_access()


def _expand_human_assignment_type() -> None:
    op.drop_constraint(
        op.f(_HUMAN_ASSIGNMENT_CHECK),
        "human_review_assignments",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_HUMAN_ASSIGNMENT_CHECK),
        "human_review_assignments",
        "assignment_type IN "
        "('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM','WAITING_OWNER_RECOVERY',"
        "'CASE_ASSIGNMENT_INHERITANCE')",
    )


def _backfill_from_review_ownership() -> None:
    op.execute(
        """
        WITH latest_owned_task AS (
            SELECT DISTINCT ON (tenant_id, case_id)
                   tenant_id,
                   case_id,
                   id AS review_task_id,
                   current_assignee_id
              FROM human_review_tasks
             WHERE current_assignee_id IS NOT NULL
             ORDER BY tenant_id, case_id, created_at DESC, id DESC
        )
        UPDATE cases AS target
           SET current_assignee_id = source.current_assignee_id,
               assignment_version = 1,
               updated_at = now()
          FROM latest_owned_task AS source
         WHERE target.tenant_id = source.tenant_id
           AND target.id = source.case_id
           AND target.current_assignee_id IS NULL
        """
    )
    op.execute(
        """
        WITH latest_owned_task AS (
            SELECT DISTINCT ON (task.tenant_id, task.case_id)
                   task.tenant_id,
                   task.case_id,
                   task.current_assignee_id,
                   COALESCE(active.assigned_by, task.current_assignee_id) AS assigned_by
              FROM human_review_tasks AS task
              LEFT JOIN human_review_assignments AS active
                ON active.tenant_id = task.tenant_id
               AND active.review_task_id = task.id
               AND active.released_at IS NULL
             WHERE task.current_assignee_id IS NOT NULL
             ORDER BY task.tenant_id, task.case_id, task.created_at DESC, task.id DESC
        )
        INSERT INTO case_assignments (
            id, tenant_id, case_id, assignee_id, assigned_by, assignment_type,
            rationale, assigned_at, released_at, created_at
        )
        SELECT gen_random_uuid(), source.tenant_id, source.case_id,
               source.current_assignee_id, source.assigned_by, 'REVIEW_TASK_BACKFILL',
               'Recovered from current review ownership', now(), NULL, now()
          FROM latest_owned_task AS source
          JOIN cases AS target
            ON target.tenant_id = source.tenant_id
           AND target.id = source.case_id
         WHERE target.assignment_version = 1
        """
    )
    op.execute(
        """
        INSERT INTO case_assignment_actions (
            id, tenant_id, case_id, action_type, from_assignee_id,
            to_assignee_id, actor_id, rationale, expected_version,
            resulting_version, occurred_at, created_at
        )
        SELECT gen_random_uuid(), tenant_id, case_id, 'BACKFILLED', NULL,
               assignee_id, assigned_by, 'Recovered from current review ownership',
               0, 1, assigned_at, created_at
          FROM case_assignments
         WHERE assignment_type = 'REVIEW_TASK_BACKFILL'
        """
    )


def _create_append_only_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION csight_case_assignment_action_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Case assignment actions are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_case_assignment_actions_append_only
        BEFORE UPDATE OR DELETE ON case_assignment_actions
        FOR EACH ROW EXECUTE FUNCTION csight_case_assignment_action_append_only()
        """
    )


def _enable_rls_and_case_access() -> None:
    tenant_expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    for table_name in _NEW_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO csight_api_role")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO csight_worker_role")
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY csight_tenant_scope ON {table_name}
            FOR ALL TO csight_api_role, csight_worker_role
            USING ({tenant_expression})
            WITH CHECK ({tenant_expression})
            """
        )

    op.execute(
        """
        CREATE FUNCTION public.csight_can_access_case(p_tenant_id uuid, p_case_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
            SELECT EXISTS (
                SELECT 1
                  FROM public.cases AS owned_case
                 WHERE owned_case.tenant_id = p_tenant_id
                   AND owned_case.id = p_case_id
                   AND (
                       NULLIF(current_setting('app.case_access_all', true), '') = 'true'
                       OR owned_case.current_assignee_id = NULLIF(
                           current_setting('app.actor_id', true), ''
                       )::uuid
                       OR EXISTS (
                           SELECT 1
                             FROM public.human_review_tasks AS task
                             JOIN public.human_review_decisions AS decision
                               ON decision.tenant_id = task.tenant_id
                              AND decision.review_task_id = task.id
                            WHERE task.tenant_id = p_tenant_id
                              AND task.case_id = p_case_id
                              AND decision.decided_by = NULLIF(
                                  current_setting('app.actor_id', true), ''
                              )::uuid
                       )
                   )
            )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.csight_can_access_case(uuid, uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.csight_can_access_case(uuid, uuid) TO csight_api_role"
    )
    for table_name, case_column in _CASE_SCOPED_TABLES:
        op.execute(
            f"""
            CREATE POLICY csight_case_owner_select ON {table_name}
            AS RESTRICTIVE FOR SELECT TO csight_api_role
            USING (public.csight_can_access_case(tenant_id, {case_column}))
            """
        )


def downgrade() -> None:
    for table_name, _case_column in reversed(_CASE_SCOPED_TABLES):
        op.execute(f"DROP POLICY csight_case_owner_select ON {table_name}")
    op.execute("DROP FUNCTION public.csight_can_access_case(uuid, uuid)")
    op.execute("DROP TRIGGER trg_case_assignment_actions_append_only ON case_assignment_actions")
    op.execute("DROP FUNCTION csight_case_assignment_action_append_only()")
    for table_name in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY csight_tenant_scope ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM csight_worker_role")
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM csight_api_role")

    op.execute(
        "UPDATE human_review_assignments SET assignment_type = 'ADMIN_ASSIGNMENT' "
        "WHERE assignment_type = 'CASE_ASSIGNMENT_INHERITANCE'"
    )
    op.drop_constraint(
        op.f(_HUMAN_ASSIGNMENT_CHECK),
        "human_review_assignments",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_HUMAN_ASSIGNMENT_CHECK),
        "human_review_assignments",
        "assignment_type IN "
        "('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM','WAITING_OWNER_RECOVERY')",
    )

    op.drop_table("case_assignment_actions")
    op.drop_index("ix_case_assignments_assignee", table_name="case_assignments")
    op.drop_index("uq_case_assignments_current", table_name="case_assignments")
    op.drop_table("case_assignments")
    op.drop_constraint(
        op.f("ck_cases_assignment_projection_consistent"),
        "cases",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_cases_assignment_version_nonnegative"),
        "cases",
        type_="check",
    )
    op.drop_constraint("fk_cases_current_assignee", "cases", type_="foreignkey")
    op.drop_column("cases", "assignment_version")
    op.drop_column("cases", "current_assignee_id")


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]
