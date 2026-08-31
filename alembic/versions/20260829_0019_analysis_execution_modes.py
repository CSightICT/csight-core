"""Add immutable analysis execution modes and fail-closed shadow lineage guards.

Revision ID: 20260829_0019_analysis_execution_modes
Revises: 20260829_0018_oidc_sessions
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260829_0019_analysis_execution_modes"
down_revision: str | None = "20260829_0018_oidc_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SHADOW_LINEAGE_TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("policy_evaluation_runs", "analysis", "analysis_run_id"),
    ("human_review_request_events", "policy", "policy_evaluation_run_id"),
    ("human_review_tasks", "policy", "policy_evaluation_run_id"),
    ("human_review_packets", "analysis", "analysis_run_id"),
    ("human_review_actions", "task", "review_task_id"),
    ("human_review_assignments", "task", "review_task_id"),
    ("human_review_decisions", "task", "review_task_id"),
    ("human_review_decision_basis", "decision", "human_review_decision_id"),
    ("case_resolutions", "task", "source_review_task_id"),
    ("external_action_intents", "resolution", "resolution_id"),
    ("case_resolution_events", "resolution", "resolution_id"),
    ("case_resolution_request_events", "resolution", "resolution_id"),
    (
        "external_action_simulation_request_events",
        "intent",
        "external_action_intent_id",
    ),
    ("external_action_simulation_attempts", "intent", "external_action_intent_id"),
    ("external_action_simulation_results", "intent", "external_action_intent_id"),
)


def _lineage_trigger_name(table_name: str) -> str:
    return f"trg_{table_name}_primary_analysis_only"


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column(
            "execution_mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PRIMARY'"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_execution_mode_allowed"),
        "analysis_runs",
        "execution_mode IN ('PRIMARY','SHADOW')",
    )
    op.create_index(
        "ix_analysis_runs_admission_nonterminal",
        "analysis_runs",
        ["tenant_id", "id"],
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING','RETRY_WAITING')"),
    )

    op.execute(
        """
        CREATE FUNCTION csight_analysis_execution_mode_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.execution_mode IS DISTINCT FROM OLD.execution_mode THEN
                RAISE EXCEPTION 'analysis execution_mode is immutable'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_analysis_runs_execution_mode_immutable';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_analysis_runs_execution_mode_immutable
        BEFORE UPDATE OF execution_mode ON analysis_runs
        FOR EACH ROW
        EXECUTE FUNCTION csight_analysis_execution_mode_immutable()
        """
    )

    op.execute(
        """
        CREATE FUNCTION csight_require_primary_analysis_lineage()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            lineage_kind text := TG_ARGV[0];
            lineage_id uuid := (to_jsonb(NEW) ->> TG_ARGV[1])::uuid;
            analysis_mode text;
        BEGIN
            IF lineage_kind = 'analysis' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM analysis_runs
                 WHERE analysis_runs.tenant_id = NEW.tenant_id
                   AND analysis_runs.id = lineage_id;
            ELSIF lineage_kind = 'policy' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM policy_evaluation_runs
                  JOIN analysis_runs
                    ON analysis_runs.tenant_id = policy_evaluation_runs.tenant_id
                   AND analysis_runs.id = policy_evaluation_runs.analysis_run_id
                 WHERE policy_evaluation_runs.tenant_id = NEW.tenant_id
                   AND policy_evaluation_runs.id = lineage_id;
            ELSIF lineage_kind = 'task' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM human_review_tasks
                  JOIN policy_evaluation_runs
                    ON policy_evaluation_runs.tenant_id = human_review_tasks.tenant_id
                   AND policy_evaluation_runs.id = human_review_tasks.policy_evaluation_run_id
                  JOIN analysis_runs
                    ON analysis_runs.tenant_id = policy_evaluation_runs.tenant_id
                   AND analysis_runs.id = policy_evaluation_runs.analysis_run_id
                 WHERE human_review_tasks.tenant_id = NEW.tenant_id
                   AND human_review_tasks.id = lineage_id;
            ELSIF lineage_kind = 'decision' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM human_review_decisions
                  JOIN human_review_tasks
                    ON human_review_tasks.tenant_id = human_review_decisions.tenant_id
                   AND human_review_tasks.id = human_review_decisions.review_task_id
                  JOIN policy_evaluation_runs
                    ON policy_evaluation_runs.tenant_id = human_review_tasks.tenant_id
                   AND policy_evaluation_runs.id = human_review_tasks.policy_evaluation_run_id
                  JOIN analysis_runs
                    ON analysis_runs.tenant_id = policy_evaluation_runs.tenant_id
                   AND analysis_runs.id = policy_evaluation_runs.analysis_run_id
                 WHERE human_review_decisions.tenant_id = NEW.tenant_id
                   AND human_review_decisions.id = lineage_id;
            ELSIF lineage_kind = 'resolution' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM case_resolutions
                  JOIN human_review_tasks
                    ON human_review_tasks.tenant_id = case_resolutions.tenant_id
                   AND human_review_tasks.id = case_resolutions.source_review_task_id
                  JOIN policy_evaluation_runs
                    ON policy_evaluation_runs.tenant_id = human_review_tasks.tenant_id
                   AND policy_evaluation_runs.id = human_review_tasks.policy_evaluation_run_id
                  JOIN analysis_runs
                    ON analysis_runs.tenant_id = policy_evaluation_runs.tenant_id
                   AND analysis_runs.id = policy_evaluation_runs.analysis_run_id
                 WHERE case_resolutions.tenant_id = NEW.tenant_id
                   AND case_resolutions.id = lineage_id;
            ELSIF lineage_kind = 'intent' THEN
                SELECT analysis_runs.execution_mode
                  INTO analysis_mode
                  FROM external_action_intents
                  JOIN case_resolutions
                    ON case_resolutions.tenant_id = external_action_intents.tenant_id
                   AND case_resolutions.id = external_action_intents.resolution_id
                  JOIN human_review_tasks
                    ON human_review_tasks.tenant_id = case_resolutions.tenant_id
                   AND human_review_tasks.id = case_resolutions.source_review_task_id
                  JOIN policy_evaluation_runs
                    ON policy_evaluation_runs.tenant_id = human_review_tasks.tenant_id
                   AND policy_evaluation_runs.id = human_review_tasks.policy_evaluation_run_id
                  JOIN analysis_runs
                    ON analysis_runs.tenant_id = policy_evaluation_runs.tenant_id
                   AND analysis_runs.id = policy_evaluation_runs.analysis_run_id
                 WHERE external_action_intents.tenant_id = NEW.tenant_id
                   AND external_action_intents.id = lineage_id;
            END IF;

            IF analysis_mode IS DISTINCT FROM 'PRIMARY' THEN
                RAISE EXCEPTION 'decision workflow requires PRIMARY analysis lineage'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_shadow_analysis_no_downstream';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table_name, lineage_kind, lineage_column in _SHADOW_LINEAGE_TRIGGERS:
        op.execute(
            f"""
            CREATE TRIGGER {_lineage_trigger_name(table_name)}
            BEFORE INSERT OR UPDATE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION csight_require_primary_analysis_lineage(
                '{lineage_kind}', '{lineage_column}'
            )
            """
        )


def downgrade() -> None:
    for table_name, _, _ in reversed(_SHADOW_LINEAGE_TRIGGERS):
        op.execute(f"DROP TRIGGER {_lineage_trigger_name(table_name)} ON {table_name}")
    op.execute("DROP FUNCTION csight_require_primary_analysis_lineage()")
    op.execute("DROP TRIGGER trg_analysis_runs_execution_mode_immutable ON analysis_runs")
    op.execute("DROP FUNCTION csight_analysis_execution_mode_immutable()")
    op.drop_index("ix_analysis_runs_admission_nonterminal", table_name="analysis_runs")
    op.drop_constraint(
        op.f("ck_analysis_runs_execution_mode_allowed"),
        "analysis_runs",
        type_="check",
    )
    op.drop_column("analysis_runs", "execution_mode")
