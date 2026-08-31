"""Split policy query building from search with durable v2 event lineage.

Revision ID: 20260831_0036_policy_query_search_events_v2
Revises: 20260831_0035_query_grounding_model_route_snapshot
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0036_policy_query_search_events_v2"
down_revision: str | None = "20260831_0035_query_grounding_model_route_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_TABLE = "policy_retrieval_runs"
_OUTBOX_TABLE = "policy_retrieval_outbox_events"
_RECOVERY_TABLE = "operational_failure_recovery_events"


def upgrade() -> None:
    op.add_column(
        _OUTBOX_TABLE,
        sa.Column(
            "event_type",
            sa.String(length=128),
            nullable=False,
            server_default="policy_retrieval.requested.v1",
        ),
    )
    op.create_check_constraint(
        op.f("ck_policy_retrieval_outbox_events_event_type_allowed"),
        _OUTBOX_TABLE,
        "event_type IN ('policy_retrieval.requested.v1', "
        "'policy_query_build.requested.v2', 'policy_search.requested.v2')",
    )
    op.drop_constraint(
        op.f("uq_policy_retrieval_outbox_run"),
        _OUTBOX_TABLE,
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_policy_retrieval_outbox_run_event_type"),
        _OUTBOX_TABLE,
        ["tenant_id", "retrieval_run_id", "event_type"],
    )
    op.drop_constraint(
        op.f("ck_operational_failure_recovery_events_topic_allowed"),
        _RECOVERY_TABLE,
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_operational_failure_recovery_events_topic_allowed"),
        _RECOVERY_TABLE,
        "topic IN ('analysis.requested.v1','policy_retrieval.requested.v1',"
        "'policy_query_build.requested.v2','policy_search.requested.v2',"
        "'grounded_explanation.requested.v1','policy_evaluation.requested.v1',"
        "'human_review.requested.v1','case_resolution.requested.v1',"
        "'external_action.simulation_requested.v1')",
    )

    for constraint_name in (
        "ck_policy_retrieval_runs_status_allowed",
        "ck_policy_retrieval_runs_status_timestamps_consistent",
        "ck_policy_retrieval_runs_execution_claim_consistent",
    ):
        op.drop_constraint(op.f(constraint_name), _RUN_TABLE, type_="check")
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_status_allowed"),
        _RUN_TABLE,
        "status IN ('QUEUED','RUNNING','SEARCH_QUEUED','SUCCEEDED','FAILED')",
    )
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_status_timestamps_consistent"),
        _RUN_TABLE,
        "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
        "(status IN ('RUNNING','SEARCH_QUEUED') AND started_at IS NOT NULL "
        "AND completed_at IS NULL) OR "
        "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
        "AND completed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_execution_claim_consistent"),
        _RUN_TABLE,
        "(status = 'RUNNING' AND claim_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
        "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE policy_retrieval_runs SET status = 'QUEUED', started_at = NULL "
            "WHERE status = 'SEARCH_QUEUED'"
        )
    )
    for constraint_name in (
        "ck_policy_retrieval_runs_execution_claim_consistent",
        "ck_policy_retrieval_runs_status_timestamps_consistent",
        "ck_policy_retrieval_runs_status_allowed",
    ):
        op.drop_constraint(op.f(constraint_name), _RUN_TABLE, type_="check")
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_status_allowed"),
        _RUN_TABLE,
        "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
    )
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_status_timestamps_consistent"),
        _RUN_TABLE,
        "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
        "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
        "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL "
        "AND completed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_policy_retrieval_runs_execution_claim_consistent"),
        _RUN_TABLE,
        "(status = 'RUNNING' AND claim_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
        "(status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
    )
    op.drop_constraint(
        op.f("ck_policy_retrieval_outbox_events_event_type_allowed"),
        _OUTBOX_TABLE,
        type_="check",
    )
    op.drop_constraint(
        op.f("uq_policy_retrieval_outbox_run_event_type"),
        _OUTBOX_TABLE,
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_policy_retrieval_outbox_run"),
        _OUTBOX_TABLE,
        ["tenant_id", "retrieval_run_id"],
    )
    op.drop_column(_OUTBOX_TABLE, "event_type")
