"""Allow explicitly marked Shadow runs into the human feedback workflow.

Revision ID: 20260910_0037_shadow_human_feedback
Revises: 20260831_0036_policy_query_search_events_v2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0037_shadow_human_feedback"
down_revision: str | None = "20260831_0036_policy_query_search_events_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_GUARD = "IF analysis_mode IS DISTINCT FROM 'PRIMARY' THEN"
_FEEDBACK_GUARD = """IF analysis_mode IS DISTINCT FROM 'PRIMARY' AND NOT (
                COALESCE(analysis_mode = 'SHADOW', false) AND (
                    (TG_TABLE_NAME = 'policy_evaluation_runs'
                     AND (to_jsonb(NEW)->>'shadow_feedback_allowed')::boolean IS TRUE)
                    OR (TG_TABLE_NAME <> 'policy_evaluation_runs' AND EXISTS (
                        SELECT 1 FROM policy_evaluation_runs AS feedback_run
                        WHERE feedback_run.tenant_id = NEW.tenant_id
                          AND feedback_run.analysis_run_id = source_analysis_id
                          AND feedback_run.shadow_feedback_allowed IS TRUE
                    ))
                )
            ) THEN"""


def _replace_lineage_function(*, restore: bool) -> None:
    # Rewrite the existing, tenant-scoped lineage traversal, not its triggers or joins.
    old_guard, new_guard = (
        (_FEEDBACK_GUARD, _OLD_GUARD) if restore else (_OLD_GUARD, _FEEDBACK_GUARD)
    )
    old_decl, new_decl = "analysis_mode text;", "analysis_mode text; source_analysis_id uuid;"
    old_select = "SELECT analysis_runs.execution_mode"
    new_select = "SELECT analysis_runs.execution_mode, analysis_runs.id"
    old_into, new_into = "INTO analysis_mode", "INTO analysis_mode, source_analysis_id"
    if restore:
        old_decl, new_decl = new_decl, old_decl
        old_select, new_select = new_select, old_select
        old_into, new_into = new_into, old_into
    statement = sa.text("""
        DO $rewrite$
        DECLARE definition text;
        BEGIN
            SELECT pg_get_functiondef('csight_require_primary_analysis_lineage()'::regprocedure)
                INTO definition;
            IF position(:old_guard IN definition) = 0 THEN
                RAISE EXCEPTION 'Unexpected Shadow lineage guard definition';
            END IF;
            definition := replace(definition, :old_guard, :new_guard);
            definition := replace(definition, :old_decl, :new_decl);
            definition := replace(definition, :old_select, :new_select);
            definition := replace(definition, :old_into, :new_into);
            EXECUTE definition;
        END;
        $rewrite$
    """).bindparams(
        old_guard=old_guard,
        new_guard=new_guard,
        old_decl=old_decl,
        new_decl=new_decl,
        old_select=old_select,
        new_select=new_select,
        old_into=old_into,
        new_into=new_into,
    )
    op.execute(str(statement.compile(compile_kwargs={"literal_binds": True})))


def upgrade() -> None:
    op.add_column(
        "policy_evaluation_runs",
        sa.Column(
            "shadow_feedback_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.execute("""
        CREATE FUNCTION csight_shadow_feedback_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.shadow_feedback_allowed IS DISTINCT FROM OLD.shadow_feedback_allowed THEN
                RAISE EXCEPTION 'Shadow feedback permission snapshot is immutable'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_shadow_feedback_immutable';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER trg_aa_shadow_feedback_immutable
        BEFORE UPDATE OF shadow_feedback_allowed ON policy_evaluation_runs
        FOR EACH ROW EXECUTE FUNCTION csight_shadow_feedback_immutable();
    """)
    _replace_lineage_function(restore=False)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM policy_evaluation_runs WHERE shadow_feedback_allowed) THEN
                RAISE EXCEPTION 'Feedback history exists; downgrade would strand it. Keep schema.';
            END IF;
        END $$;
    """)
    _replace_lineage_function(restore=True)
    op.execute("DROP TRIGGER trg_aa_shadow_feedback_immutable ON policy_evaluation_runs")
    op.execute("DROP FUNCTION csight_shadow_feedback_immutable()")
    op.drop_column("policy_evaluation_runs", "shadow_feedback_allowed")
