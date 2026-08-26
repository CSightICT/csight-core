"""Add immutable citation packs and grounded explanation runs.

Revision ID: 20260827_0009
Revises: 20260826_0008
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0009"
down_revision: str | None = "20260826_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "grounding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("model_artifact", sa.String(255), nullable=False),
        sa.Column("model_revision", sa.String(255), nullable=True),
        sa.Column("prompt_name", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("input_schema_version", sa.String(32), nullable=False),
        sa.Column("output_schema_version", sa.String(32), nullable=False),
        sa.Column("validator_name", sa.String(128), nullable=False),
        sa.Column("validator_version", sa.String(64), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grounding_profiles")),
        sa.UniqueConstraint(
            "profile_name", "profile_version", name="uq_grounding_profiles_version"
        ),
    )
    op.create_table(
        "policy_citation_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("retrieval_profile_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_policy_citation_packs_retrieval_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_policy_citation_packs_case",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_citation_packs_content_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            "retrieval_profile_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_citation_packs_retrieval_profile_hash_lower_hex"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_citation_packs")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_citation_packs_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "retrieval_run_id", name="uq_policy_citation_packs_retrieval_run"
        ),
    )
    op.create_table(
        "policy_citation_pack_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("citation_pack_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=False),
        sa.Column("policy_clause_id", sa.String(320), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("section_path", postgresql.ARRAY(sa.String(500)), nullable=False),
        sa.Column("clause_type", sa.String(64), nullable=False),
        sa.Column("clause_text", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("retrieval_mode", sa.String(32), nullable=False),
        sa.Column("query_strategy", sa.String(32), nullable=False),
        sa.Column("matched_query_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_profile_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citation_pack_id"],
            ["policy_citation_packs.tenant_id", "policy_citation_packs.id"],
            name="fk_policy_citation_pack_items_pack",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_policy_citation_pack_items_clause",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("rank > 0", name=op.f("ck_policy_citation_pack_items_rank_positive")),
        sa.CheckConstraint(
            "citation_id ~ '^CIT-[0-9]{3}$'",
            name=op.f("ck_policy_citation_pack_items_citation_id_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_citation_pack_items")),
        sa.UniqueConstraint(
            "tenant_id", "citation_pack_id", "rank", name="uq_citation_pack_items_rank"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "citation_pack_id",
            "citation_id",
            name="uq_citation_pack_items_citation_id",
        ),
    )
    op.create_table(
        "grounded_explanation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("citation_pack_id", sa.Uuid(), nullable=False),
        sa.Column("grounding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
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
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_grounded_explanation_runs_retrieval",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citation_pack_id"],
            ["policy_citation_packs.tenant_id", "policy_citation_packs.id"],
            name="fk_grounded_explanation_runs_pack",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_grounded_explanation_runs_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name="fk_grounded_explanation_runs_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["grounding_profile_id"],
            ["grounding_profiles.id"],
            name="fk_grounded_explanation_runs_profile",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_grounded_explanation_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_grounded_explanation_runs_request_hash_lower_hex"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_grounded_explanation_runs_status_timestamps_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grounded_explanation_runs")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_grounded_explanation_runs_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_grounded_explanation_runs_tenant_key"
        ),
    )
    op.create_index(
        "ix_grounded_explanation_runs_case_created",
        "grounded_explanation_runs",
        ["tenant_id", "case_id", "created_at", "id"],
    )
    op.create_table(
        "grounded_explanation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("grounded_explanation_run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("policy_statements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unresolved_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("model_revision", sa.String(255), nullable=True),
        sa.Column("prompt_name", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("input_token_count", sa.Integer(), nullable=True),
        sa.Column("output_token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "grounded_explanation_run_id"],
            ["grounded_explanation_runs.tenant_id", "grounded_explanation_runs.id"],
            name="fk_grounded_explanation_results_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grounded_explanation_results")),
        sa.UniqueConstraint(
            "tenant_id",
            "grounded_explanation_run_id",
            name="uq_grounded_explanation_results_run",
        ),
    )
    op.create_table(
        "grounded_explanation_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("grounded_explanation_run_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "grounded_explanation_run_id"],
            ["grounded_explanation_runs.tenant_id", "grounded_explanation_runs.id"],
            name="fk_grounded_explanation_outbox_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
            name=op.f("ck_grounded_explanation_outbox_events_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grounded_explanation_outbox_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "grounded_explanation_run_id",
            name="uq_grounded_explanation_outbox_run",
        ),
    )


def downgrade() -> None:
    op.drop_table("grounded_explanation_outbox_events")
    op.drop_table("grounded_explanation_results")
    op.drop_index(
        "ix_grounded_explanation_runs_case_created", table_name="grounded_explanation_runs"
    )
    op.drop_table("grounded_explanation_runs")
    op.drop_table("policy_citation_pack_items")
    op.drop_table("policy_citation_packs")
    op.drop_table("grounding_profiles")
