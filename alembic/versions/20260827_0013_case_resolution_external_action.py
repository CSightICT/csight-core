"""Add Case Resolution and deterministic external Action Intent simulation.

Revision ID: 20260827_0013_case_resolution_external_action
Revises: 20260827_0012_async_reliability
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0013_case_resolution_external_action"
down_revision: str | None = "20260827_0012_async_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOLUTION_STATUSES = (
    "'DECISION_RECORDED','ACTION_NOT_REQUIRED','MANUAL_FOLLOW_UP_REQUIRED',"
    "'ACTION_NEEDS_INPUT','ACTION_READY','ACTION_DRY_RUN_PENDING',"
    "'ACTION_DRY_RUN_VALIDATED','ACTION_DRY_RUN_FAILED'"
)
OUTBOX_STATUSES = "'PENDING','PROCESSING','PUBLISHED','CONSUMED','FAILED'"
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


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated_at() -> sa.Column[object]:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _outbox_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consumer_attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consumer_last_error", sa.String(1000), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )


def _outbox_constraints(table_name: str) -> tuple[sa.CheckConstraint, ...]:
    return (
        sa.CheckConstraint(
            f"status IN ({OUTBOX_STATUSES})",
            name=op.f(f"ck_{table_name}_status_allowed"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f(f"ck_{table_name}_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "consumer_attempt_count >= 0",
            name=op.f(f"ck_{table_name}_consumer_attempts_valid"),
        ),
        sa.CheckConstraint(
            OUTBOX_STATE_CONSISTENCY,
            name=op.f(f"ck_{table_name}_state_consistent"),
        ),
    )


def upgrade() -> None:
    # Sprint 5C keeps the requested descriptive revision identifier.  Earlier
    # Alembic baselines used the default VARCHAR(32), which cannot store it.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_table(
        "case_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("source_review_task_id", sa.Uuid(), nullable=False),
        sa.Column("source_human_decision_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("mapping_name", sa.String(128), nullable=False),
        sa.Column("mapping_version", sa.String(64), nullable=False),
        sa.Column("resolution_schema_version", sa.String(32), nullable=False),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "invalid_fields",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        sa.Column(
            "execution_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_case_resolutions_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_review_task_id"],
            ["human_review_tasks.tenant_id", "human_review_tasks.id"],
            name="fk_case_resolutions_review_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_human_decision_id"],
            ["human_review_decisions.tenant_id", "human_review_decisions.id"],
            name="fk_case_resolutions_human_decision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"status IN ({RESOLUTION_STATUSES})",
            name=op.f("ck_case_resolutions_status_allowed"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_case_resolutions_version_positive")),
        sa.CheckConstraint(
            "mapping_name = 'human_decision_to_external_action' "
            "AND mapping_version = '1.0.0' AND resolution_schema_version = '1.0.0'",
            name=op.f("ck_case_resolutions_versions_supported"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(missing_fields) = 'array'",
            name=op.f("ck_case_resolutions_missing_fields_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(invalid_fields) = 'array'",
            name=op.f("ck_case_resolutions_invalid_fields_array"),
        ),
        sa.CheckConstraint(
            "execution_attempt_count >= 0",
            name=op.f("ck_case_resolutions_execution_attempts_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'ACTION_DRY_RUN_PENDING' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND execution_attempt_count > 0) OR "
            "(status <> 'ACTION_DRY_RUN_PENDING' AND claim_token IS NULL "
            "AND lease_expires_at IS NULL)",
            name=op.f("ck_case_resolutions_execution_claim_consistent"),
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL)",
            name=op.f("ck_case_resolutions_failure_fields_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_resolutions")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_resolutions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "case_id", "id", name="uq_case_resolutions_tenant_case_id"
        ),
        sa.UniqueConstraint("tenant_id", "case_id", name="uq_case_resolutions_tenant_case"),
    )
    op.create_index(
        "ix_case_resolutions_tenant_status",
        "case_resolutions",
        ["tenant_id", "status", "updated_at", "id"],
    )

    op.create_table(
        "external_action_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("human_decision_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("order_ref", sa.String(255), nullable=False),
        sa.Column("product_ref", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("shipping_address_ref", sa.String(255), nullable=True),
        sa.Column("mapping_name", sa.String(128), nullable=False),
        sa.Column("mapping_version", sa.String(64), nullable=False),
        sa.Column("intent_schema_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_external_action_intents_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "human_decision_id"],
            ["human_review_decisions.tenant_id", "human_review_decisions.id"],
            name="fk_external_action_intents_human_decision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action_type IN ('REFUND','EXCHANGE','RESHIPMENT','REPAIR')",
            name=op.f("ck_external_action_intents_type_allowed"),
        ),
        sa.CheckConstraint(
            "mode = 'DRY_RUN'", name=op.f("ck_external_action_intents_dry_run_only")
        ),
        sa.CheckConstraint(
            "length(btrim(order_ref)) BETWEEN 1 AND 255",
            name=op.f("ck_external_action_intents_order_ref_valid"),
        ),
        sa.CheckConstraint(
            "product_ref IS NULL OR length(btrim(product_ref)) BETWEEN 1 AND 255",
            name=op.f("ck_external_action_intents_product_ref_valid"),
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0",
            name=op.f("ck_external_action_intents_amount_positive"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_external_action_intents_currency_valid"),
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity BETWEEN 1 AND 1000",
            name=op.f("ck_external_action_intents_quantity_valid"),
        ),
        sa.CheckConstraint(
            "shipping_address_ref IS NULL OR length(btrim(shipping_address_ref)) BETWEEN 1 AND 255",
            name=op.f("ck_external_action_intents_shipping_address_ref_valid"),
        ),
        sa.CheckConstraint(
            "(action_type = 'REFUND' AND product_ref IS NULL AND amount IS NOT NULL "
            "AND currency IS NOT NULL AND quantity IS NULL AND shipping_address_ref IS NULL) OR "
            "(action_type IN ('EXCHANGE','RESHIPMENT') AND product_ref IS NOT NULL "
            "AND amount IS NULL AND currency IS NULL AND quantity IS NOT NULL "
            "AND shipping_address_ref IS NOT NULL) OR "
            "(action_type = 'REPAIR' AND product_ref IS NOT NULL AND amount IS NULL "
            "AND currency IS NULL AND quantity IS NOT NULL AND shipping_address_ref IS NULL)",
            name=op.f("ck_external_action_intents_typed_input_consistent"),
        ),
        sa.CheckConstraint(
            "mapping_name = 'human_decision_to_external_action' "
            "AND mapping_version = '1.0.0' AND intent_schema_version = '1.0.0'",
            name=op.f("ck_external_action_intents_versions_supported"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_external_action_intents_content_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_action_intents")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_external_action_intents_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "case_id", "id", name="uq_external_action_intents_tenant_case_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "resolution_id", name="uq_external_action_intents_resolution"
        ),
    )
    op.create_index(
        "ix_external_action_intents_case_created",
        "external_action_intents",
        ["tenant_id", "case_id", "created_at", "id"],
    )

    op.create_table(
        "case_resolution_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(64), nullable=True),
        sa.Column("to_status", sa.String(64), nullable=False),
        sa.Column("human_decision_id", sa.Uuid(), nullable=True),
        sa.Column("external_action_intent_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_case_resolution_events_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "human_decision_id"],
            ["human_review_decisions.tenant_id", "human_review_decisions.id"],
            name="fk_case_resolution_events_human_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "external_action_intent_id"],
            ["external_action_intents.tenant_id", "external_action_intents.id"],
            name="fk_case_resolution_events_intent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "sequence >= 1", name=op.f("ck_case_resolution_events_sequence_positive")
        ),
        sa.CheckConstraint(
            f"event_type IN ({RESOLUTION_STATUSES})",
            name=op.f("ck_case_resolution_events_type_allowed"),
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({RESOLUTION_STATUSES})",
            name=op.f("ck_case_resolution_events_from_status_allowed"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({RESOLUTION_STATUSES})",
            name=op.f("ck_case_resolution_events_to_status_allowed"),
        ),
        sa.CheckConstraint(
            "event_type = to_status",
            name=op.f("ck_case_resolution_events_event_matches_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name=op.f("ck_case_resolution_events_payload_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_resolution_events")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_resolution_events_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "resolution_id", "sequence", name="uq_case_resolution_events_sequence"
        ),
    )
    op.create_index(
        "ix_case_resolution_events_case_sequence",
        "case_resolution_events",
        ["tenant_id", "case_id", "sequence", "id"],
    )

    op.create_table(
        "case_resolution_request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("human_decision_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        *_outbox_columns(),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_case_resolution_request_events_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "human_decision_id"],
            ["human_review_decisions.tenant_id", "human_review_decisions.id"],
            name="fk_case_resolution_request_events_human_decision",
            ondelete="RESTRICT",
        ),
        *_outbox_constraints("case_resolution_request_events"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_resolution_request_events")),
        sa.UniqueConstraint(
            "tenant_id", "human_decision_id", name="uq_case_resolution_request_events_decision"
        ),
    )
    op.create_index(
        "ix_case_resolution_request_events_pending_dispatch",
        "case_resolution_request_events",
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_case_resolution_request_events_processing_claimed",
        "case_resolution_request_events",
        ["claimed_at", "id"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )

    op.create_table(
        "external_action_simulation_request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("external_action_intent_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        *_outbox_columns(),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "external_action_intent_id"],
            [
                "external_action_intents.tenant_id",
                "external_action_intents.case_id",
                "external_action_intents.id",
            ],
            name="fk_external_action_simulation_requests_intent",
            ondelete="RESTRICT",
        ),
        *_outbox_constraints("external_action_simulation_request_events"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_action_simulation_request_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_action_intent_id",
            name="uq_external_action_simulation_requests_intent",
        ),
    )
    op.create_index(
        "ix_external_action_simulation_requests_pending_dispatch",
        "external_action_simulation_request_events",
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_external_action_simulation_requests_processing_claimed",
        "external_action_simulation_request_events",
        ["claimed_at", "id"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )

    op.create_table(
        "external_action_simulation_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("external_action_intent_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_external_action_simulation_attempts_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "external_action_intent_id"],
            [
                "external_action_intents.tenant_id",
                "external_action_intents.case_id",
                "external_action_intents.id",
            ],
            name="fk_external_action_simulation_attempts_intent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name=op.f("ck_external_action_simulation_attempts_attempt_number_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_external_action_simulation_attempts_status_allowed"),
        ),
        sa.CheckConstraint(
            "mode IN ('DRY_RUN','LIVE')",
            name=op.f("ck_external_action_simulation_attempts_mode_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL) OR "
            "(status <> 'RUNNING' AND completed_at IS NOT NULL)",
            name=op.f("ck_external_action_simulation_attempts_completion_consistent"),
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL)",
            name=op.f("ck_external_action_simulation_attempts_failure_fields_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_action_simulation_attempts")),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_external_action_simulation_attempts_tenant_id"
        ),
        sa.UniqueConstraint("execution_token", name="uq_external_action_simulation_attempts_token"),
        sa.UniqueConstraint(
            "tenant_id",
            "external_action_intent_id",
            "attempt_number",
            name="uq_external_action_simulation_attempts_number",
        ),
    )
    op.create_index(
        "ix_external_action_simulation_attempts_intent",
        "external_action_simulation_attempts",
        ["tenant_id", "external_action_intent_id", "attempt_number"],
    )

    op.create_table(
        "external_action_simulation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=False),
        sa.Column("external_action_intent_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("side_effects_performed", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        sa.Column("simulated_request", postgresql.JSONB(), nullable=False),
        sa.Column("simulated_response", postgresql.JSONB(), nullable=False),
        sa.Column("result_schema_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "resolution_id"],
            ["case_resolutions.tenant_id", "case_resolutions.case_id", "case_resolutions.id"],
            name="fk_external_action_simulation_results_resolution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id", "external_action_intent_id"],
            [
                "external_action_intents.tenant_id",
                "external_action_intents.case_id",
                "external_action_intents.id",
            ],
            name="fk_external_action_simulation_results_intent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "simulation_attempt_id"],
            [
                "external_action_simulation_attempts.tenant_id",
                "external_action_simulation_attempts.id",
            ],
            name="fk_external_action_simulation_results_attempt",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "outcome IN ('VALIDATED','FAILED')",
            name=op.f("ck_external_action_simulation_results_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "mode IN ('DRY_RUN','LIVE')",
            name=op.f("ck_external_action_simulation_results_mode_allowed"),
        ),
        sa.CheckConstraint(
            "side_effects_performed = false",
            name=op.f("ck_external_action_simulation_results_no_side_effects"),
        ),
        sa.CheckConstraint(
            "(outcome = 'VALIDATED' AND failure_code IS NULL AND failure_message IS NULL) OR "
            "(outcome = 'FAILED' AND failure_code IS NOT NULL AND failure_message IS NOT NULL)",
            name=op.f("ck_external_action_simulation_results_outcome_failure_consistent"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(simulated_request) = 'object'",
            name=op.f("ck_external_action_simulation_results_request_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(simulated_response) = 'object'",
            name=op.f("ck_external_action_simulation_results_response_object"),
        ),
        sa.CheckConstraint(
            "result_schema_version = '1.0.0' AND content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_external_action_simulation_results_version_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_action_simulation_results")),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_external_action_simulation_results_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "external_action_intent_id",
            name="uq_external_action_simulation_results_intent",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "simulation_attempt_id",
            name="uq_external_action_simulation_results_attempt",
        ),
    )


def downgrade() -> None:
    op.drop_table("external_action_simulation_results")
    op.drop_table("external_action_simulation_attempts")
    op.drop_table("external_action_simulation_request_events")
    op.drop_table("case_resolution_request_events")
    op.drop_table("case_resolution_events")
    op.drop_table("external_action_intents")
    op.drop_table("case_resolutions")
