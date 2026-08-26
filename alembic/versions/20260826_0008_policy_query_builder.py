"""Add append-only policy query-builder retrieval runs.

Revision ID: 20260826_0008
Revises: 20260826_0007
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0008"
down_revision: str | None = "20260826_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_llm_results_v2_tenant_id",
        "llm_extraction_results_v2",
        ["tenant_id", "id"],
    )
    op.create_table(
        "policy_query_builder_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=True),
        sa.Column("model_artifact", sa.String(255), nullable=True),
        sa.Column("model_revision", sa.String(255), nullable=True),
        sa.Column("prompt_name", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("rule_name", sa.String(128), nullable=True),
        sa.Column("rule_version", sa.String(64), nullable=True),
        sa.Column("rule_hash", sa.String(64), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("max_queries", sa.Integer(), nullable=False),
        sa.Column("max_query_tokens", sa.Integer(), nullable=False),
        sa.Column("filter_hint_policy", sa.String(128), nullable=False),
        sa.Column("filter_hint_policy_version", sa.String(64), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "strategy IN ('RAW','DETERMINISTIC','LLM')",
            name=op.f("ck_policy_query_builder_profiles_strategy_allowed"),
        ),
        sa.CheckConstraint(
            "max_queries BETWEEN 1 AND 3 AND max_query_tokens > 0",
            name=op.f("ck_policy_query_builder_profiles_limits_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_query_builder_profiles")),
        sa.UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_query_builder_profiles_version"
        ),
    )
    op.create_table(
        "policy_retrieval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("text_result_id", sa.Uuid(), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("query_builder_profile_id", sa.Uuid(), nullable=False),
        sa.Column("base_index_version_id", sa.Uuid(), nullable=False),
        sa.Column("base_retrieval_profile_hash", sa.String(64), nullable=False),
        sa.Column("multi_query_fusion_profile", sa.String(128), nullable=False),
        sa.Column("multi_query_fusion_version", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["query_builder_profile_id"],
            ["policy_query_builder_profiles.id"],
            name="fk_policy_retrieval_runs_query_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["base_index_version_id"],
            ["policy_index_versions.id"],
            name="fk_policy_retrieval_runs_index",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_policy_retrieval_runs_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_policy_retrieval_runs_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "text_result_id"],
            ["llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"],
            name="fk_policy_retrieval_runs_text_v2",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name="fk_policy_retrieval_runs_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "strategy IN ('RAW','DETERMINISTIC','LLM')",
            name=op.f("ck_policy_retrieval_runs_strategy_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_policy_retrieval_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "top_k BETWEEN 1 AND 50", name=op.f("ck_policy_retrieval_runs_top_k_valid")
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_retrieval_runs_request_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR (status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR (status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_policy_retrieval_runs_status_timestamps_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_runs")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_retrieval_runs_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_policy_retrieval_runs_tenant_key"
        ),
    )
    op.create_index(
        "ix_policy_retrieval_runs_tenant_case_created",
        "policy_retrieval_runs",
        ["tenant_id", "case_id", "created_at", "id"],
    )
    op.create_table(
        "policy_retrieval_run_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("query_source", sa.String(64), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("filter_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_policy_retrieval_run_queries_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "query_id ~ '^Q[1-3]$'", name=op.f("ck_policy_retrieval_run_queries_query_id_valid")
        ),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 3", name=op.f("ck_policy_retrieval_run_queries_position_valid")
        ),
        sa.CheckConstraint(
            "query_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_retrieval_run_queries_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            "(query_source = 'CASE_CUSTOMER_MESSAGE' AND query_text IS NULL) OR (query_source = 'GENERATED' AND length(btrim(query_text)) > 0)",
            name=op.f("ck_policy_retrieval_run_queries_raw_not_duplicated"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_run_queries")),
        sa.UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "query_id",
            name="uq_policy_retrieval_run_queries_query",
        ),
    )
    op.create_table(
        "policy_retrieval_run_hits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=False),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("best_query_rank", sa.Integer(), nullable=False),
        sa.Column("matched_query_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("per_query_ranks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_policy_retrieval_run_hits_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_policy_retrieval_run_hits_clause",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rank > 0 AND best_query_rank > 0 AND fusion_score > 0",
            name=op.f("ck_policy_retrieval_run_hits_ranking_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_run_hits")),
        sa.UniqueConstraint(
            "tenant_id", "retrieval_run_id", "rank", name="uq_policy_retrieval_run_hits_rank"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "policy_clause_row_id",
            name="uq_policy_retrieval_run_hits_clause",
        ),
    )
    op.create_table(
        "policy_retrieval_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_policy_retrieval_outbox_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
            name=op.f("ck_policy_retrieval_outbox_events_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_outbox_events")),
        sa.UniqueConstraint("tenant_id", "retrieval_run_id", name="uq_policy_retrieval_outbox_run"),
    )


def downgrade() -> None:
    op.drop_table("policy_retrieval_outbox_events")
    op.drop_table("policy_retrieval_run_hits")
    op.drop_table("policy_retrieval_run_queries")
    op.drop_index(
        "ix_policy_retrieval_runs_tenant_case_created", table_name="policy_retrieval_runs"
    )
    op.drop_table("policy_retrieval_runs")
    op.drop_table("policy_query_builder_profiles")
    op.drop_constraint(
        "uq_llm_results_v2_tenant_id",
        "llm_extraction_results_v2",
        type_="unique",
    )
