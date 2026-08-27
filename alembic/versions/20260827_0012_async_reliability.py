"""Add fenced dispatch, consumer audit, and worker execution leases.

Revision ID: 20260827_0012_async_reliability
Revises: 20260827_0011_human_review
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0012_async_reliability"
down_revision: str | None = "20260827_0011_human_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTBOX_TABLES = (
    "policy_retrieval_outbox_events",
    "grounded_explanation_outbox_events",
    "policy_evaluation_outbox_events",
    "human_review_request_events",
)

OUTBOX_INDEX_PREFIXES = {
    "policy_retrieval_outbox_events": "policy_retrieval_outbox",
    "grounded_explanation_outbox_events": "grounded_explanation_outbox",
    "policy_evaluation_outbox_events": "policy_evaluation_outbox",
    "human_review_request_events": "human_review_request_events",
}

RUN_OUTBOX_PAIRS = (
    (
        "policy_retrieval_runs",
        "policy_retrieval_outbox_events",
        "retrieval_run_id",
    ),
    (
        "grounded_explanation_runs",
        "grounded_explanation_outbox_events",
        "grounded_explanation_run_id",
    ),
    (
        "policy_evaluation_runs",
        "policy_evaluation_outbox_events",
        "policy_evaluation_run_id",
    ),
)

RUN_CASE_IDENTITIES = (
    (
        "policy_retrieval_runs",
        "policy_retrieval_outbox_events",
        "retrieval_run_id",
        "uq_policy_retrieval_runs_tenant_case_id",
        "fk_policy_retrieval_outbox_run_case",
    ),
    (
        "grounded_explanation_runs",
        "grounded_explanation_outbox_events",
        "grounded_explanation_run_id",
        "uq_grounded_explanation_runs_tenant_case_id",
        "fk_grounded_explanation_outbox_run_case",
    ),
    (
        "policy_evaluation_runs",
        "policy_evaluation_outbox_events",
        "policy_evaluation_run_id",
        "uq_policy_evaluation_runs_tenant_case_id",
        "fk_policy_evaluation_outbox_run_case",
    ),
)

HUMAN_REVIEW_ASSIGNEE_CHECK = "ck_human_review_tasks_assignee_status_consistent"
HUMAN_REVIEW_BASIS_LEGACY_CHECK = "ck_human_review_decision_basis_one_typed_reference"
HUMAN_REVIEW_BASIS_TYPED_CHECK = "ck_human_review_decision_basis_typed_reference_consistent"
HUMAN_REVIEW_CITATION_IDENTITY_UNIQUE = "uq_policy_citation_pack_items_tenant_id_clause"
HUMAN_REVIEW_CITATION_BASIS_FK = "fk_human_review_decision_basis_citation_clause"
HUMAN_REVIEW_POLICY_RUN_CASE_FK = "fk_human_review_request_events_policy_run_case"

OUTBOX_STATE_CONSISTENCY = (
    "(status = 'PENDING' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL) OR "
    "(status = 'PROCESSING' AND claimed_at IS NOT NULL AND claim_token IS NOT NULL "
    "AND claimed_by IS NOT NULL AND published_at IS NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL AND attempt_count > 0) OR "
    "(status = 'PUBLISHED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NOT NULL AND consumed_at IS NULL "
    "AND failed_at IS NULL AND attempt_count > 0) OR "
    "(status = 'CONSUMED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND published_at IS NOT NULL AND consumed_at IS NOT NULL "
    "AND failed_at IS NULL AND attempt_count > 0 AND consumer_attempt_count > 0) OR "
    "(status = 'FAILED' AND claimed_at IS NULL AND claim_token IS NULL "
    "AND claimed_by IS NULL AND consumed_at IS NULL AND failed_at IS NOT NULL "
    "AND failure_code IS NOT NULL AND attempt_count > 0 "
    "AND (last_error IS NOT NULL OR consumer_last_error IS NOT NULL))"
)

RUN_EXECUTION_CLAIM_CONSISTENCY = (
    "(status = 'RUNNING' AND claim_token IS NOT NULL "
    "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
    "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)"
)

HUMAN_REVIEW_BASIS_TYPED_REFERENCE_CONSISTENCY = (
    "(basis_type = 'POLICY_RULE_RESULT' AND policy_rule_result_id IS NOT NULL "
    "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
    "AND case_evidence_id IS NULL AND analysis_result_id IS NULL) OR "
    "(basis_type = 'POLICY_CITATION' AND policy_rule_result_id IS NULL "
    "AND policy_clause_row_id IS NOT NULL AND citation_item_id IS NOT NULL "
    "AND case_evidence_id IS NULL AND analysis_result_id IS NULL) OR "
    "(basis_type = 'CASE_EVIDENCE' AND policy_rule_result_id IS NULL "
    "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
    "AND case_evidence_id IS NOT NULL AND analysis_result_id IS NULL) OR "
    "(basis_type = 'ANALYSIS_RESULT' AND policy_rule_result_id IS NULL "
    "AND policy_clause_row_id IS NULL AND citation_item_id IS NULL "
    "AND case_evidence_id IS NULL AND analysis_result_id IS NOT NULL)"
)


def _add_outbox_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("claim_token", sa.Uuid(), nullable=True))
    op.add_column(table_name, sa.Column("claimed_by", sa.String(length=255), nullable=True))
    op.add_column(table_name, sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("last_error", sa.String(length=1000), nullable=True))
    op.add_column(table_name, sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        table_name,
        sa.Column(
            "consumer_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        table_name,
        sa.Column("consumer_last_error", sa.String(length=1000), nullable=True),
    )
    op.add_column(table_name, sa.Column("failure_code", sa.String(length=128), nullable=True))
    op.add_column(table_name, sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def _normalize_legacy_outbox(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET attempt_count = CASE
                    WHEN status IN ('PROCESSING','PUBLISHED','FAILED')
                        THEN GREATEST(attempt_count, 1)
                    ELSE attempt_count
                END,
                status = CASE WHEN status = 'PROCESSING' THEN 'PENDING' ELSE status END,
                available_at = CASE WHEN status = 'PROCESSING' THEN now() ELSE available_at END,
                published_at = CASE WHEN status = 'PUBLISHED' THEN created_at ELSE NULL END,
                last_error = CASE
                    WHEN status = 'FAILED' THEN 'Legacy outbox dispatch failure.'
                    ELSE NULL
                END,
                failure_code = CASE
                    WHEN status = 'FAILED' THEN 'LEGACY_OUTBOX_FAILED'
                    ELSE NULL
                END,
                failed_at = CASE WHEN status = 'FAILED' THEN created_at ELSE NULL END
            """
        )
    )


def _replace_outbox_constraints_and_indexes(table_name: str) -> None:
    index_prefix = OUTBOX_INDEX_PREFIXES[table_name]
    op.drop_constraint(
        op.f(f"ck_{table_name}_status_allowed"),
        table_name,
        type_="check",
    )
    op.create_check_constraint(
        op.f(f"ck_{table_name}_status_allowed"),
        table_name,
        "status IN ('PENDING','PROCESSING','PUBLISHED','CONSUMED','FAILED')",
    )
    op.create_check_constraint(
        op.f(f"ck_{table_name}_attempt_count_nonnegative"),
        table_name,
        "attempt_count >= 0",
    )
    op.create_check_constraint(
        op.f(f"ck_{table_name}_consumer_attempts_valid"),
        table_name,
        "consumer_attempt_count >= 0",
    )
    op.create_check_constraint(
        op.f(f"ck_{table_name}_state_consistent"),
        table_name,
        OUTBOX_STATE_CONSISTENCY,
    )
    op.create_index(
        f"ix_{index_prefix}_pending_dispatch",
        table_name,
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        f"ix_{index_prefix}_processing_claimed",
        table_name,
        ["claimed_at", "id"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )


def _add_run_execution_lease(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "execution_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(table_name, sa.Column("claim_token", sa.Uuid(), nullable=True))
    op.add_column(
        table_name, sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def _recover_legacy_running_run(
    *,
    run_table: str,
    outbox_table: str,
    outbox_run_column: str,
) -> None:
    # Migration must run with dispatchers/workers quiesced. Existing RUNNING rows are returned to
    # their original durable event so the new leased worker can reclaim them safely.
    op.execute(
        sa.text(
            f"""
            UPDATE {outbox_table} AS event
            SET status = 'PENDING',
                available_at = now(),
                claimed_at = NULL,
                claim_token = NULL,
                claimed_by = NULL,
                published_at = NULL,
                last_error = 'Recovered by async reliability migration.',
                consumed_at = NULL,
                consumer_last_error = NULL,
                failure_code = NULL,
                failed_at = NULL
            FROM {run_table} AS run
            WHERE run.status = 'RUNNING'
              AND event.tenant_id = run.tenant_id
              AND event.{outbox_run_column} = run.id
              AND event.status IN ('PROCESSING','PUBLISHED')
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {run_table}
            SET status = 'QUEUED',
                started_at = NULL,
                completed_at = NULL,
                failure_code = NULL,
                failure_message = NULL,
                claim_token = NULL,
                lease_expires_at = NULL
            WHERE status = 'RUNNING'
            """
        )
    )


def _create_run_execution_constraints(table_name: str) -> None:
    op.create_check_constraint(
        op.f(f"ck_{table_name}_execution_attempts_valid"),
        table_name,
        "execution_attempt_count >= 0",
    )
    op.create_check_constraint(
        op.f(f"ck_{table_name}_execution_claim_consistent"),
        table_name,
        RUN_EXECUTION_CLAIM_CONSISTENCY,
    )
    op.create_index(
        f"ix_{table_name}_running_lease",
        table_name,
        ["lease_expires_at", "id"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def _upgrade_resolved_assignment_projection() -> None:
    # Assignment history owns the interval. A terminal task has no current queue assignee.
    op.execute(
        sa.text(
            """
            UPDATE human_review_assignments AS assignment
            SET released_at = task.resolved_at
            FROM human_review_tasks AS task
            WHERE task.tenant_id = assignment.tenant_id
              AND task.id = assignment.review_task_id
              AND task.status = 'RESOLVED'
              AND assignment.released_at IS NULL
            """
        )
    )
    op.drop_constraint(
        op.f(HUMAN_REVIEW_ASSIGNEE_CHECK),
        "human_review_tasks",
        type_="check",
    )
    op.execute(
        sa.text(
            """
            UPDATE human_review_tasks
            SET current_assignee_id = NULL
            WHERE status = 'RESOLVED'
            """
        )
    )
    op.create_check_constraint(
        op.f(HUMAN_REVIEW_ASSIGNEE_CHECK),
        "human_review_tasks",
        "(status = 'CLAIMED' AND current_assignee_id IS NOT NULL) OR "
        "(status <> 'CLAIMED' AND current_assignee_id IS NULL)",
    )


def _upgrade_decision_basis_integrity() -> None:
    op.create_unique_constraint(
        HUMAN_REVIEW_CITATION_IDENTITY_UNIQUE,
        "policy_citation_pack_items",
        ["tenant_id", "id", "policy_clause_row_id"],
    )
    op.create_foreign_key(
        HUMAN_REVIEW_CITATION_BASIS_FK,
        "human_review_decision_basis",
        "policy_citation_pack_items",
        ["tenant_id", "citation_item_id", "policy_clause_row_id"],
        ["tenant_id", "id", "policy_clause_row_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f(HUMAN_REVIEW_BASIS_LEGACY_CHECK),
        "human_review_decision_basis",
        type_="check",
    )
    op.create_check_constraint(
        op.f(HUMAN_REVIEW_BASIS_TYPED_CHECK),
        "human_review_decision_basis",
        HUMAN_REVIEW_BASIS_TYPED_REFERENCE_CONSISTENCY,
    )


def _upgrade_run_case_identity() -> None:
    for run_table, outbox_table, run_column, unique_name, foreign_key_name in RUN_CASE_IDENTITIES:
        op.create_unique_constraint(
            unique_name,
            run_table,
            ["tenant_id", "case_id", "id"],
        )
        op.create_foreign_key(
            foreign_key_name,
            outbox_table,
            run_table,
            ["tenant_id", "case_id", run_column],
            ["tenant_id", "case_id", "id"],
            ondelete="RESTRICT",
        )
    op.create_foreign_key(
        HUMAN_REVIEW_POLICY_RUN_CASE_FK,
        "human_review_request_events",
        "policy_evaluation_runs",
        ["tenant_id", "case_id", "policy_evaluation_run_id"],
        ["tenant_id", "case_id", "id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    for table_name in OUTBOX_TABLES:
        _add_outbox_columns(table_name)
        _normalize_legacy_outbox(table_name)
        _replace_outbox_constraints_and_indexes(table_name)

    for run_table, _, _ in RUN_OUTBOX_PAIRS:
        _add_run_execution_lease(run_table)

    for run_table, outbox_table, outbox_run_column in RUN_OUTBOX_PAIRS:
        _recover_legacy_running_run(
            run_table=run_table,
            outbox_table=outbox_table,
            outbox_run_column=outbox_run_column,
        )
        _create_run_execution_constraints(run_table)

    _upgrade_resolved_assignment_projection()
    _upgrade_decision_basis_integrity()
    _upgrade_run_case_identity()


def _prepare_downgrade_active_state() -> None:
    # The 0011 dispatchers cannot recover PROCESSING rows and its workers do not understand
    # execution leases. Recreate the durable wake-up before removing either safety mechanism.
    for run_table, outbox_table, outbox_run_column in RUN_OUTBOX_PAIRS:
        op.execute(
            sa.text(
                f"""
                DO $downgrade_guard$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM {run_table} AS run
                        WHERE run.status = 'RUNNING'
                          AND NOT EXISTS (
                              SELECT 1
                              FROM {outbox_table} AS event
                              WHERE event.tenant_id = run.tenant_id
                                AND event.{outbox_run_column} = run.id
                          )
                    ) THEN
                        RAISE EXCEPTION
                            'Cannot downgrade async reliability with an orphan RUNNING aggregate';
                    END IF;
                END
                $downgrade_guard$
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {outbox_table} AS event
                SET status = 'PENDING',
                    available_at = now(),
                    claimed_at = NULL,
                    claim_token = NULL,
                    claimed_by = NULL,
                    published_at = NULL,
                    last_error = 'Recovered for 0011 downgrade.',
                    consumed_at = NULL,
                    consumer_last_error = NULL,
                    failure_code = NULL,
                    failed_at = NULL
                FROM {run_table} AS run
                WHERE run.status = 'RUNNING'
                  AND event.tenant_id = run.tenant_id
                  AND event.{outbox_run_column} = run.id
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {run_table}
                SET status = 'QUEUED',
                    started_at = NULL,
                    completed_at = NULL,
                    failure_code = NULL,
                    failure_message = NULL,
                    claim_token = NULL,
                    lease_expires_at = NULL
                WHERE status = 'RUNNING'
                """
            )
        )

    for table_name in OUTBOX_TABLES:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET status = 'PENDING',
                    available_at = now(),
                    claimed_at = NULL,
                    claim_token = NULL,
                    claimed_by = NULL,
                    published_at = NULL,
                    last_error = 'Recovered stale dispatcher claim for 0011 downgrade.',
                    consumed_at = NULL,
                    consumer_last_error = NULL,
                    failure_code = NULL,
                    failed_at = NULL
                WHERE status = 'PROCESSING'
                """
            )
        )


def _downgrade_outbox(table_name: str) -> None:
    index_prefix = OUTBOX_INDEX_PREFIXES[table_name]
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET status = 'PUBLISHED',
                consumed_at = NULL,
                consumer_last_error = NULL,
                failure_code = NULL,
                failed_at = NULL
            WHERE status = 'CONSUMED'
            """
        )
    )
    op.drop_index(
        f"ix_{index_prefix}_processing_claimed",
        table_name=table_name,
    )
    op.drop_index(
        f"ix_{index_prefix}_pending_dispatch",
        table_name=table_name,
    )
    op.drop_constraint(op.f(f"ck_{table_name}_state_consistent"), table_name, type_="check")
    op.drop_constraint(
        op.f(f"ck_{table_name}_consumer_attempts_valid"),
        table_name,
        type_="check",
    )
    op.drop_constraint(
        op.f(f"ck_{table_name}_attempt_count_nonnegative"),
        table_name,
        type_="check",
    )
    op.drop_constraint(op.f(f"ck_{table_name}_status_allowed"), table_name, type_="check")
    op.create_check_constraint(
        op.f(f"ck_{table_name}_status_allowed"),
        table_name,
        "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
    )
    for column_name in (
        "failed_at",
        "failure_code",
        "consumer_last_error",
        "consumer_attempt_count",
        "consumed_at",
        "last_error",
        "published_at",
        "claimed_by",
        "claim_token",
        "claimed_at",
    ):
        op.drop_column(table_name, column_name)


def _downgrade_run(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_running_lease", table_name=table_name)
    op.drop_constraint(
        op.f(f"ck_{table_name}_execution_claim_consistent"),
        table_name,
        type_="check",
    )
    op.drop_constraint(
        op.f(f"ck_{table_name}_execution_attempts_valid"),
        table_name,
        type_="check",
    )
    op.drop_column(table_name, "lease_expires_at")
    op.drop_column(table_name, "claim_token")
    op.drop_column(table_name, "execution_attempt_count")


def _downgrade_run_case_identity() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE human_review_request_events DROP CONSTRAINT IF EXISTS "
            f'"{HUMAN_REVIEW_POLICY_RUN_CASE_FK}"'
        )
    )
    for run_table, outbox_table, _, unique_name, foreign_key_name in reversed(RUN_CASE_IDENTITIES):
        op.execute(
            sa.text(f'ALTER TABLE {outbox_table} DROP CONSTRAINT IF EXISTS "{foreign_key_name}"')
        )
        op.execute(sa.text(f'ALTER TABLE {run_table} DROP CONSTRAINT IF EXISTS "{unique_name}"'))


def _downgrade_decision_basis_integrity() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE human_review_decision_basis DROP CONSTRAINT IF EXISTS "
            f'"{HUMAN_REVIEW_BASIS_TYPED_CHECK}"'
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE human_review_decision_basis DROP CONSTRAINT IF EXISTS "
            f'"{HUMAN_REVIEW_BASIS_LEGACY_CHECK}"'
        )
    )
    op.create_check_constraint(
        op.f(HUMAN_REVIEW_BASIS_LEGACY_CHECK),
        "human_review_decision_basis",
        "num_nonnulls(policy_rule_result_id, citation_item_id, case_evidence_id,"
        "analysis_result_id) = 1",
    )
    op.execute(
        sa.text(
            "ALTER TABLE human_review_decision_basis DROP CONSTRAINT IF EXISTS "
            f'"{HUMAN_REVIEW_CITATION_BASIS_FK}"'
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE policy_citation_pack_items DROP CONSTRAINT IF EXISTS "
            f'"{HUMAN_REVIEW_CITATION_IDENTITY_UNIQUE}"'
        )
    )


def _downgrade_resolved_assignment_projection() -> None:
    op.drop_constraint(
        op.f(HUMAN_REVIEW_ASSIGNEE_CHECK),
        "human_review_tasks",
        type_="check",
    )
    op.execute(
        sa.text(
            """
            DO $resolved_assignee_guard$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM human_review_tasks AS task
                    WHERE task.status = 'RESOLVED'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM human_review_decisions AS decision
                          WHERE decision.tenant_id = task.tenant_id
                            AND decision.review_task_id = task.id
                      )
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade with a RESOLVED task that has no human decision';
                END IF;
            END
            $resolved_assignee_guard$
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE human_review_tasks AS task
            SET current_assignee_id = decision.decided_by
            FROM human_review_decisions AS decision
            WHERE task.status = 'RESOLVED'
              AND decision.tenant_id = task.tenant_id
              AND decision.review_task_id = task.id
            """
        )
    )
    op.create_check_constraint(
        op.f(HUMAN_REVIEW_ASSIGNEE_CHECK),
        "human_review_tasks",
        "(status IN ('CLAIMED','RESOLVED') AND current_assignee_id IS NOT NULL) OR "
        "(status NOT IN ('CLAIMED','RESOLVED') AND current_assignee_id IS NULL)",
    )


def downgrade() -> None:
    _prepare_downgrade_active_state()
    _downgrade_run_case_identity()
    _downgrade_decision_basis_integrity()
    _downgrade_resolved_assignment_projection()
    for run_table, _, _ in reversed(RUN_OUTBOX_PAIRS):
        _downgrade_run(run_table)
    for table_name in reversed(OUTBOX_TABLES):
        _downgrade_outbox(table_name)
