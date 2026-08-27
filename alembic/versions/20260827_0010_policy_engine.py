"""Add immutable policy rules and append-only deterministic evaluations.

Revision ID: 20260827_0010_policy_engine
Revises: 20260827_0009
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0010_policy_engine"
down_revision: str | None = "20260827_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "policy_rule_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_name", sa.String(128), nullable=False),
        sa.Column("rule_set_version", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_corpus_name", sa.String(255), nullable=False),
        sa.Column("source_corpus_version", sa.String(64), nullable=False),
        sa.Column("source_corpus_hash", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("rule_schema_version", sa.String(64), nullable=False),
        sa.Column("field_registry_version", sa.String(64), nullable=False),
        sa.Column("operator_registry_version", sa.String(64), nullable=False),
        sa.Column("aggregation_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_policy_rule_sets_tenant", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_policy_rule_sets_dates_valid"),
        ),
        sa.CheckConstraint(
            "source_type = 'SYNTHETIC_REFERENCE'",
            name=op.f("ck_policy_rule_sets_source_type_allowed"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND source_corpus_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_rule_sets_hashes_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_rule_sets")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_rule_sets_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "rule_set_name", "rule_set_version", name="uq_policy_rule_sets_version"
        ),
    )
    op.create_table(
        "policy_rule_set_activations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_name", sa.String(128), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_reason", sa.String(255), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_set_id"],
            ["policy_rule_sets.tenant_id", "policy_rule_sets.id"],
            name="fk_policy_rule_set_activations_rule_set",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["users.tenant_id", "users.id"],
            name="fk_policy_rule_set_activations_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at >= activated_at",
            name=op.f("ck_policy_rule_set_activations_dates_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_rule_set_activations")),
    )
    op.create_index(
        "uq_policy_rule_set_activations_one_active",
        "policy_rule_set_activations",
        ["tenant_id", "rule_set_name"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "policy_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("prohibit_final_decision", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_set_id"],
            ["policy_rule_sets.tenant_id", "policy_rule_sets.id"],
            name="fk_policy_rules_rule_set",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("priority BETWEEN 0 AND 10000", name=op.f("ck_policy_rules_priority")),
        sa.CheckConstraint(
            "prohibit_final_decision", name=op.f("ck_policy_rules_no_final_decision")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) > 0",
            name=op.f("ck_policy_rules_conditions_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(effects) = 'array' AND jsonb_array_length(effects) > 0",
            name=op.f("ck_policy_rules_effects_nonempty"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_rules")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_rules_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "rule_set_id", "rule_id", "rule_version", name="uq_policy_rules_identity"
        ),
    )
    op.create_table(
        "policy_rule_source_clauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_rule_id", sa.Uuid(), nullable=False),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("clause_id", sa.String(320), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_rule_id"],
            ["policy_rules.tenant_id", "policy_rules.id"],
            name="fk_policy_rule_source_clauses_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_policy_rule_source_clauses_clause",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_rule_source_clauses")),
        sa.UniqueConstraint(
            "tenant_id",
            "policy_rule_id",
            "policy_clause_row_id",
            name="uq_policy_rule_source_clause",
        ),
    )
    op.create_table(
        "policy_evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_version", sa.String(64), nullable=False),
        sa.Column("rule_set_hash", sa.String(64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("summary_status", sa.String(64), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_policy_evaluation_runs_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_policy_evaluation_runs_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_set_id"],
            ["policy_rule_sets.tenant_id", "policy_rule_sets.id"],
            name="fk_policy_evaluation_runs_rule_set",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name="fk_policy_evaluation_runs_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_policy_evaluation_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_policy_evaluation_runs_timestamps_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_evaluation_runs")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_evaluation_runs_tenant_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_policy_evaluation_runs_key"),
    )
    op.create_index(
        "ix_policy_evaluation_runs_case_created",
        "policy_evaluation_runs",
        ["tenant_id", "case_id", "created_at", "id"],
    )
    op.create_table(
        "policy_evaluation_input_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("llm_extraction_result_v2_id", sa.Uuid(), nullable=False),
        sa.Column("vision_analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("alignment_result_id", sa.Uuid(), nullable=True),
        sa.Column("input_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source_qualification_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_policy_evaluation_input_snapshots_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "llm_extraction_result_v2_id"],
            ["llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"],
            name="fk_policy_evaluation_input_snapshots_extraction",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_evaluation_input_snapshots")),
        sa.UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_policy_evaluation_snapshot_run"
        ),
    )
    op.create_table(
        "policy_rule_evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("policy_rule_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("rule_status", sa.String(32), nullable=False),
        sa.Column("source_clause_ids", postgresql.ARRAY(sa.String(320)), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_policy_rule_evaluation_results_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_rule_id"],
            ["policy_rules.tenant_id", "policy_rules.id"],
            name="fk_policy_rule_evaluation_results_rule",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rule_status IN ('MATCHED','NOT_MATCHED','INDETERMINATE','NOT_APPLICABLE')",
            name=op.f("ck_policy_rule_evaluation_results_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_rule_evaluation_results")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_rule_evaluation_results_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "policy_evaluation_run_id",
            "policy_rule_id",
            name="uq_policy_rule_evaluation_result",
        ),
    )
    op.create_table(
        "policy_condition_evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_rule_evaluation_result_id", sa.Uuid(), nullable=False),
        sa.Column("condition_index", sa.Integer(), nullable=False),
        sa.Column("condition_status", sa.String(32), nullable=False),
        sa.Column("actual_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason_code", sa.String(128), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_rule_evaluation_result_id"],
            ["policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"],
            name="fk_policy_condition_evaluation_results_rule_result",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "condition_status IN ('SATISFIED','UNSATISFIED','UNKNOWN','NOT_EVALUATED','NOT_APPLICABLE')",
            name=op.f("ck_policy_condition_evaluation_results_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_condition_evaluation_results")),
        sa.UniqueConstraint(
            "tenant_id",
            "policy_rule_evaluation_result_id",
            "condition_index",
            name="uq_policy_condition_evaluation_result",
        ),
    )
    op.create_table(
        "policy_evaluation_effects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_rule_evaluation_result_id", sa.Uuid(), nullable=False),
        sa.Column("effect_type", sa.String(64), nullable=False),
        sa.Column("effect_value", sa.String(128), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_rule_evaluation_result_id"],
            ["policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"],
            name="fk_policy_evaluation_effects_rule_result",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "effect_type IN ('MARK_REVIEW_ELIGIBILITY','REQUIRE_ADDITIONAL_EVIDENCE','REQUIRE_HUMAN_REVIEW','REQUIRE_MANAGER_REVIEW','PROHIBIT_AUTOMATION','FLAG_POLICY_EXCEPTION')",
            name=op.f("ck_policy_evaluation_effects_type_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_evaluation_effects")),
    )
    op.create_table(
        "policy_evaluation_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_policy_evaluation_outbox_events_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
            name=op.f("ck_policy_evaluation_outbox_events_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_evaluation_outbox_events")),
        sa.UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_policy_evaluation_outbox_run"
        ),
    )


def downgrade() -> None:
    op.drop_table("policy_evaluation_outbox_events")
    op.drop_table("policy_evaluation_effects")
    op.drop_table("policy_condition_evaluation_results")
    op.drop_table("policy_rule_evaluation_results")
    op.drop_table("policy_evaluation_input_snapshots")
    op.drop_index("ix_policy_evaluation_runs_case_created", table_name="policy_evaluation_runs")
    op.drop_table("policy_evaluation_runs")
    op.drop_table("policy_rule_source_clauses")
    op.drop_table("policy_rules")
    op.drop_index(
        "uq_policy_rule_set_activations_one_active", table_name="policy_rule_set_activations"
    )
    op.drop_table("policy_rule_set_activations")
    op.drop_table("policy_rule_sets")
