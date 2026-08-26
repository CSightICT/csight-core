"""Create Sprint 2 analysis, attempt, result, idempotency, and outbox tables.

Revision ID: 20260826_0003
Revises: 20260826_0002
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0003"
down_revision: str | None = "20260826_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANALYSIS_PIPELINES = ("product_defect_text_extraction",)
ANALYSIS_PIPELINE_VERSIONS = ("1.0.0",)
ANALYSIS_TRIGGERS = ("USER_REQUEST",)
ANALYSIS_RUN_STATUSES = ("QUEUED", "RUNNING", "RETRY_WAITING", "SUCCEEDED", "FAILED")
ANALYSIS_STAGE_TYPES = (
    "TEXT_EXTRACTION",
    "VISION_ANALYSIS",
    "EVIDENCE_ALIGNMENT",
    "POLICY_EVALUATION",
    "ROUTING",
    "REPORT_GENERATION",
)
ANALYSIS_ATTEMPT_STATUSES = (
    "RUNNING",
    "RETRY_WAITING",
    "SUCCEEDED",
    "FAILED",
    "ABANDONED",
)
EXTRACTED_REQUESTED_ACTIONS = (
    "REFUND",
    "EXCHANGE",
    "RESHIPMENT",
    "REPAIR",
    "INFORMATION",
    "OTHER",
    "UNKNOWN",
)
OUTBOX_STATUSES = ("PENDING", "PROCESSING", "PUBLISHED", "FAILED")
ANALYSIS_IDEMPOTENCY_OPERATIONS = ("analysis.create.v1",)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_name", sa.String(length=128), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(correlation_id)) > 0",
            name=op.f("ck_analysis_runs_correlation_id_nonempty"),
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL) OR (status <> 'FAILED')",
            name=op.f("ck_analysis_runs_failed_has_code"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_analysis_runs_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name=op.f("ck_analysis_runs_failure_fields_consistent"),
        ),
        sa.CheckConstraint(
            f"pipeline_name IN ({_sql_values(ANALYSIS_PIPELINES)})",
            name=op.f("ck_analysis_runs_pipeline_name_allowed"),
        ),
        sa.CheckConstraint(
            f"pipeline_version IN ({_sql_values(ANALYSIS_PIPELINE_VERSIONS)})",
            name=op.f("ck_analysis_runs_pipeline_version_allowed"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_analysis_runs_request_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_RUN_STATUSES)})",
            name=op.f("ck_analysis_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status IN ('RUNNING', 'RETRY_WAITING') AND started_at IS NOT NULL "
            "AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED', 'FAILED') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name=op.f("ck_analysis_runs_status_timestamps_consistent"),
        ),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR (failure_code IS NULL AND failure_message IS NULL)",
            name=op.f("ck_analysis_runs_succeeded_has_no_failure"),
        ),
        sa.CheckConstraint(
            f"trigger_type IN ({_sql_values(ANALYSIS_TRIGGERS)})",
            name=op.f("ck_analysis_runs_trigger_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name=op.f("fk_analysis_runs_tenant_id_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "requested_by"),
            ("users.tenant_id", "users.id"),
            name=op.f("fk_analysis_runs_tenant_id_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_analysis_runs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_runs")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_analysis_runs_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name=op.f("uq_analysis_runs_tenant_idempotency_key"),
        ),
    )
    op.create_index(
        "ix_analysis_runs_tenant_case_created_id",
        "analysis_runs",
        ["tenant_id", "case_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_runs_tenant_case_status_created_id",
        "analysis_runs",
        ["tenant_id", "case_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_runs_tenant_case_pipeline_created_id",
        "analysis_runs",
        ["tenant_id", "case_id", "pipeline_name", "pipeline_version", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "analysis_stage_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=True),
        sa.Column("prompt_name", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_schema_version", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("execution_provider_name", sa.String(length=128), nullable=True),
        sa.Column("execution_model_name", sa.String(length=255), nullable=True),
        sa.Column("execution_model_version", sa.String(length=128), nullable=True),
        sa.Column("execution_model_revision", sa.String(length=255), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("input_token_count", sa.Integer(), nullable=True),
        sa.Column("output_token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_analysis_stage_runs_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND failure_code IS NOT NULL) OR status <> 'FAILED'",
            name=op.f("ck_analysis_stage_runs_failed_has_code"),
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name=op.f("ck_analysis_stage_runs_failure_fields_consistent"),
        ),
        sa.CheckConstraint(
            "input_token_count IS NULL OR input_token_count >= 0",
            name=op.f("ck_analysis_stage_runs_input_token_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name=op.f("ck_analysis_stage_runs_latency_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "(latency_ms IS NULL AND execution_provider_name IS NULL "
            "AND execution_model_name IS NULL AND execution_model_version IS NULL "
            "AND execution_model_revision IS NULL AND provider_request_id IS NULL "
            "AND input_token_count IS NULL AND output_token_count IS NULL) OR "
            "(latency_ms IS NOT NULL AND execution_provider_name IS NOT NULL "
            "AND execution_model_name IS NOT NULL AND execution_model_version IS NOT NULL)",
            name=op.f("ck_analysis_stage_runs_provider_execution_consistent"),
        ),
        sa.CheckConstraint(
            "output_token_count IS NULL OR output_token_count >= 0",
            name=op.f("ck_analysis_stage_runs_output_token_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'RETRY_WAITING' AND next_attempt_at IS NOT NULL) OR "
            "(status <> 'RETRY_WAITING' AND next_attempt_at IS NULL)",
            name=op.f("ck_analysis_stage_runs_retry_schedule_consistent"),
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'RUNNING' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_analysis_stage_runs_running_claim_consistent"),
        ),
        sa.CheckConstraint(
            f"stage_type IN ({_sql_values(ANALYSIS_STAGE_TYPES)})",
            name=op.f("ck_analysis_stage_runs_stage_type_allowed"),
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_RUN_STATUSES)})",
            name=op.f("ck_analysis_stage_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND attempt_count = 0 AND started_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status IN ('RUNNING', 'RETRY_WAITING') AND attempt_count > 0 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status = 'SUCCEEDED' AND attempt_count > 0 AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'FAILED' AND attempt_count >= 0 AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name=op.f("ck_analysis_stage_runs_status_timestamps_consistent"),
        ),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR (failure_code IS NULL AND failure_message IS NULL)",
            name=op.f("ck_analysis_stage_runs_succeeded_has_no_failure"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_analysis_stage_runs_tenant_id_analysis_run_id_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_analysis_stage_runs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_stage_runs")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_analysis_stage_runs_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "id",
            name=op.f("uq_analysis_stage_runs_tenant_analysis_run_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "stage_type",
            name=op.f("uq_analysis_stage_runs_tenant_run_stage_type"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "id",
            "stage_type",
            name=op.f("uq_analysis_stage_runs_tenant_run_id_stage_type"),
        ),
    )
    op.create_index(
        "ix_analysis_stage_runs_tenant_run_created_id",
        "analysis_stage_runs",
        ["tenant_id", "analysis_run_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_stage_runs_running_lease",
        "analysis_stage_runs",
        ["lease_expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_index(
        "ix_analysis_stage_runs_retry_schedule",
        "analysis_stage_runs",
        ["next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'RETRY_WAITING'"),
    )

    op.create_table(
        "analysis_stage_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=True),
        sa.Column("prompt_name", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_schema_version", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("execution_provider_name", sa.String(length=128), nullable=True),
        sa.Column("execution_model_name", sa.String(length=255), nullable=True),
        sa.Column("execution_model_version", sa.String(length=128), nullable=True),
        sa.Column("execution_model_revision", sa.String(length=255), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("input_token_count", sa.Integer(), nullable=True),
        sa.Column("output_token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name=op.f("ck_analysis_stage_attempts_attempt_number_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND completed_at IS NULL) OR "
            "(status <> 'RUNNING' AND completed_at IS NOT NULL)",
            name=op.f("ck_analysis_stage_attempts_completion_consistent"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('FAILED', 'RETRY_WAITING', 'ABANDONED') OR failure_code IS NOT NULL",
            name=op.f("ck_analysis_stage_attempts_failure_outcome_has_code"),
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL AND failure_message IS NULL AND failure_retryable IS NULL) OR "
            "(failure_code IS NOT NULL AND failure_message IS NOT NULL "
            "AND failure_retryable IS NOT NULL)",
            name=op.f("ck_analysis_stage_attempts_failure_fields_consistent"),
        ),
        sa.CheckConstraint(
            "input_token_count IS NULL OR input_token_count >= 0",
            name=op.f("ck_analysis_stage_attempts_input_token_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name=op.f("ck_analysis_stage_attempts_latency_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "(latency_ms IS NULL AND execution_provider_name IS NULL "
            "AND execution_model_name IS NULL AND execution_model_version IS NULL "
            "AND execution_model_revision IS NULL AND provider_request_id IS NULL "
            "AND input_token_count IS NULL AND output_token_count IS NULL) OR "
            "(latency_ms IS NOT NULL AND execution_provider_name IS NOT NULL "
            "AND execution_model_name IS NOT NULL AND execution_model_version IS NOT NULL)",
            name=op.f("ck_analysis_stage_attempts_provider_execution_consistent"),
        ),
        sa.CheckConstraint(
            "output_token_count IS NULL OR output_token_count >= 0",
            name=op.f("ck_analysis_stage_attempts_output_token_count_nonnegative"),
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(ANALYSIS_ATTEMPT_STATUSES)})",
            name=op.f("ck_analysis_stage_attempts_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
            ),
            name=op.f("fk_analysis_stage_attempts_tenant_run_stage_analysis_stage_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_analysis_stage_attempts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_stage_attempts")),
        sa.UniqueConstraint(
            "execution_token",
            name=op.f("uq_analysis_stage_attempts_execution_token"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "stage_run_id",
            "attempt_number",
            name=op.f("uq_analysis_stage_attempts_tenant_stage_attempt_number"),
        ),
    )
    op.create_index(
        "ix_analysis_stage_attempts_tenant_stage_attempt",
        "analysis_stage_attempts",
        ["tenant_id", "stage_run_id", "attempt_number"],
        unique=False,
    )

    op.create_table(
        "llm_extraction_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage_type",
            sa.String(length=64),
            server_default=sa.text("'TEXT_EXTRACTION'"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False),
        sa.Column("issue_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("claims", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_action", sa.String(length=32), nullable=False),
        sa.Column(
            "missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(claims) = 'array'",
            name=op.f("ck_llm_extraction_results_claims_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(issue_types) = 'array'",
            name=op.f("ck_llm_extraction_results_issue_types_array"),
        ),
        sa.CheckConstraint(
            "jsonb_array_length(issue_types) > 0",
            name=op.f("ck_llm_extraction_results_issue_types_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(language)) > 0",
            name=op.f("ck_llm_extraction_results_language_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(missing_information) = 'array'",
            name=op.f("ck_llm_extraction_results_missing_information_array"),
        ),
        sa.CheckConstraint(
            f"requested_action IN ({_sql_values(EXTRACTED_REQUESTED_ACTIONS)})",
            name=op.f("ck_llm_extraction_results_requested_action_allowed"),
        ),
        sa.CheckConstraint(
            "length(btrim(schema_version)) > 0",
            name=op.f("ck_llm_extraction_results_schema_version_nonempty"),
        ),
        sa.CheckConstraint(
            "stage_type = 'TEXT_EXTRACTION'",
            name=op.f("ck_llm_extraction_results_stage_type_text_extraction"),
        ),
        sa.CheckConstraint(
            "length(summary) <= 4000",
            name=op.f("ck_llm_extraction_results_summary_max_length"),
        ),
        sa.CheckConstraint(
            "length(btrim(summary)) > 0",
            name=op.f("ck_llm_extraction_results_summary_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id", "stage_type"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
                "analysis_stage_runs.stage_type",
            ),
            name=op.f("fk_llm_results_tenant_run_stage_type_stage_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_llm_extraction_results_tenant_run_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_llm_extraction_results_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_extraction_results")),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            name=op.f("uq_llm_extraction_results_tenant_analysis_run"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "stage_run_id",
            name=op.f("uq_llm_extraction_results_tenant_stage_run"),
        ),
    )
    op.create_index(
        "ix_llm_extraction_results_tenant_run",
        "llm_extraction_results",
        ["tenant_id", "analysis_run_id"],
        unique=False,
    )

    op.create_table(
        "analysis_request_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_analysis_request_idempotency_records_expires_after_created"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_analysis_request_idempotency_records_key_nonempty"),
        ),
        sa.CheckConstraint(
            f"operation IN ({_sql_values(ANALYSIS_IDEMPOTENCY_OPERATIONS)})",
            name=op.f("ck_analysis_request_idempotency_records_operation_allowed"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_analysis_request_idempotency_records_request_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            "response_status = 202",
            name=op.f("ck_analysis_request_idempotency_records_response_accepted"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "case_id"),
            ("cases.tenant_id", "cases.id"),
            name=op.f("fk_analysis_request_idempotency_tenant_case_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_analysis_request_idempotency_tenant_run_analysis_runs"),
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_analysis_request_idempotency_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_analysis_request_idempotency_records"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "operation",
            "idempotency_key",
            name=op.f("uq_analysis_request_idempotency_tenant_operation_key"),
        ),
    )
    op.create_index(
        "ix_analysis_request_idempotency_expires_at",
        "analysis_request_idempotency_records",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_version", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_by", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "aggregate_type = 'analysis_run'",
            name=op.f("ck_outbox_events_aggregate_type_analysis_run"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_outbox_events_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "event_type = 'analysis.requested.v1'",
            name=op.f("ck_outbox_events_event_type_allowed"),
        ),
        sa.CheckConstraint(
            "event_version = '1.0'",
            name=op.f("ck_outbox_events_event_version_allowed"),
        ),
        sa.CheckConstraint(
            "(payload - ARRAY['event_id','event_type','event_version','tenant_id','case_id',"
            "'analysis_run_id','stage_run_id','correlation_id','occurred_at']) = '{}'::jsonb",
            name=op.f("ck_outbox_events_payload_allowed_keys"),
        ),
        sa.CheckConstraint(
            "payload->>'event_id' = id::text AND payload->>'event_type' = event_type AND "
            "payload->>'event_version' = event_version AND "
            "payload->>'tenant_id' = tenant_id::text AND "
            "payload->>'analysis_run_id' = aggregate_id::text",
            name=op.f("ck_outbox_events_payload_identity_consistent"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name=op.f("ck_outbox_events_payload_object"),
        ),
        sa.CheckConstraint(
            "payload ?& ARRAY['event_id','event_type','event_version','tenant_id','case_id',"
            "'analysis_run_id','stage_run_id','correlation_id','occurred_at']",
            name=op.f("ck_outbox_events_payload_required_keys"),
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(OUTBOX_STATUSES)})",
            name=op.f("ck_outbox_events_status_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL) OR "
            "(status = 'PROCESSING' AND claimed_at IS NOT NULL AND claim_token IS NOT NULL "
            "AND claimed_by IS NOT NULL AND published_at IS NULL AND attempt_count > 0) OR "
            "(status = 'PUBLISHED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NOT NULL AND attempt_count > 0) OR "
            "(status = 'FAILED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL AND attempt_count > 0 "
            "AND last_error IS NOT NULL)",
            name=op.f("ck_outbox_events_status_claim_timestamps_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "aggregate_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_outbox_events_tenant_aggregate_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name=op.f("fk_outbox_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_events_pending_dispatch",
        "outbox_events",
        ["available_at", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_outbox_events_processing_claimed",
        "outbox_events",
        ["claimed_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )
    op.create_index(
        "ix_outbox_events_tenant_aggregate_created_id",
        "outbox_events",
        ["tenant_id", "aggregate_type", "aggregate_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_tenant_aggregate_created_id",
        table_name="outbox_events",
    )
    op.drop_index("ix_outbox_events_processing_claimed", table_name="outbox_events")
    op.drop_index("ix_outbox_events_pending_dispatch", table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index(
        "ix_analysis_request_idempotency_expires_at",
        table_name="analysis_request_idempotency_records",
    )
    op.drop_table("analysis_request_idempotency_records")

    op.drop_index(
        "ix_llm_extraction_results_tenant_run",
        table_name="llm_extraction_results",
    )
    op.drop_table("llm_extraction_results")

    op.drop_index(
        "ix_analysis_stage_attempts_tenant_stage_attempt",
        table_name="analysis_stage_attempts",
    )
    op.drop_table("analysis_stage_attempts")

    op.drop_index(
        "ix_analysis_stage_runs_retry_schedule",
        table_name="analysis_stage_runs",
    )
    op.drop_index(
        "ix_analysis_stage_runs_running_lease",
        table_name="analysis_stage_runs",
    )
    op.drop_index(
        "ix_analysis_stage_runs_tenant_run_created_id",
        table_name="analysis_stage_runs",
    )
    op.drop_table("analysis_stage_runs")

    op.drop_index(
        "ix_analysis_runs_tenant_case_pipeline_created_id",
        table_name="analysis_runs",
    )
    op.drop_index(
        "ix_analysis_runs_tenant_case_status_created_id",
        table_name="analysis_runs",
    )
    op.drop_index(
        "ix_analysis_runs_tenant_case_created_id",
        table_name="analysis_runs",
    )
    op.drop_table("analysis_runs")
