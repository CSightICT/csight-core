"""Add immutable terminal Resolution review-report snapshots.

Revision ID: 20260827_0014_review_report_poc_metrics
Revises: 20260827_0013_case_resolution_external_action
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0014_review_report_poc_metrics"
down_revision: str | None = "20260827_0013_case_resolution_external_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_IDENTITY_UNIQUE = "uq_case_resolution_events_tenant_case_resolution_id"
CHECK_RENAMES = (
    (
        "external_action_simulation_attempts",
        "ck_external_action_simulation_attempts_failure_fields_c_8797",
        "ck_external_action_simulation_attempts_failure_consistent",
    ),
    (
        "external_action_simulation_request_events",
        "ck_external_action_simulation_request_events_attempt_co_3278",
        "ck_external_action_simulation_request_events_attempts_valid",
    ),
    (
        "external_action_simulation_request_events",
        "ck_external_action_simulation_request_events_consumer_a_7c21",
        "ck_external_action_simulation_request_events_consumer_valid",
    ),
    (
        "external_action_simulation_results",
        "ck_external_action_simulation_results_outcome_failure_c_68de",
        "ck_external_action_simulation_results_outcome_consistent",
    ),
)


def upgrade() -> None:
    for table_name, old_name, new_name in CHECK_RENAMES:
        op.execute(sa.text(f"ALTER TABLE {table_name} RENAME CONSTRAINT {old_name} TO {new_name}"))
    op.create_unique_constraint(
        EVENT_IDENTITY_UNIQUE,
        "case_resolution_events",
        ["tenant_id", "case_id", "resolution_id", "id"],
    )
    op.create_table(
        "review_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_version", sa.Integer(), nullable=False),
        sa.Column("terminal_event_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("case_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("analysis_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("review_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("resolution_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("dry_run_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("qualification_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("data_scope", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_review_reports_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id", "terminal_event_id"],
            [
                "case_resolution_events.tenant_id",
                "case_resolution_events.case_id",
                "case_resolution_events.resolution_id",
                "case_resolution_events.id",
            ],
            name="fk_review_reports_terminal_event",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "resolution_version >= 1",
            name=op.f("ck_review_reports_resolution_version_positive"),
        ),
        sa.CheckConstraint(
            "schema_version = 'review_report/1.0.0'",
            name=op.f("ck_review_reports_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(case_snapshot) = 'object' "
            "AND jsonb_typeof(analysis_snapshot) = 'object' "
            "AND jsonb_typeof(policy_snapshot) = 'object' "
            "AND jsonb_typeof(review_snapshot) = 'object' "
            "AND jsonb_typeof(resolution_snapshot) = 'object' "
            "AND jsonb_typeof(dry_run_snapshot) = 'object' "
            "AND jsonb_typeof(qualification_snapshot) = 'object' "
            "AND jsonb_typeof(data_scope) = 'object'",
            name=op.f("ck_review_reports_snapshots_object"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_review_reports_content_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_reports")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_review_reports_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "resolution_id",
            "resolution_version",
            name="uq_review_reports_resolution_version",
        ),
        sa.UniqueConstraint(
            "tenant_id", "terminal_event_id", name="uq_review_reports_terminal_event"
        ),
    )
    op.create_index(
        "ix_review_reports_case_latest",
        "review_reports",
        ["tenant_id", "case_id", "resolution_version", "generated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_reports_case_latest", table_name="review_reports")
    op.drop_table("review_reports")
    op.drop_constraint(
        EVENT_IDENTITY_UNIQUE,
        "case_resolution_events",
        type_="unique",
    )
    for table_name, old_name, new_name in reversed(CHECK_RENAMES):
        op.execute(sa.text(f"ALTER TABLE {table_name} RENAME CONSTRAINT {new_name} TO {old_name}"))
