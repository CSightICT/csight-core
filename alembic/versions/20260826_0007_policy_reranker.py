"""Persist versioned policy reranker and retrieval execution profiles.

Revision ID: 20260826_0007
Revises: 20260826_0006
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0007"
down_revision: str | None = "20260826_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_reranker_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("model_artifact", sa.String(255), nullable=False),
        sa.Column("model_revision", sa.String(255), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("instruction_hash", sa.String(64), nullable=False),
        sa.Column("query_template_name", sa.String(128), nullable=False),
        sa.Column("query_template_version", sa.String(64), nullable=False),
        sa.Column("query_template_hash", sa.String(64), nullable=False),
        sa.Column("document_template_name", sa.String(128), nullable=False),
        sa.Column("document_template_version", sa.String(64), nullable=False),
        sa.Column("document_template_hash", sa.String(64), nullable=False),
        sa.Column("max_query_tokens", sa.Integer(), nullable=False),
        sa.Column("max_document_tokens", sa.Integer(), nullable=False),
        sa.Column("max_pair_tokens", sa.Integer(), nullable=False),
        sa.Column("candidate_k", sa.Integer(), nullable=False),
        sa.Column("final_k", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("device", sa.String(32), nullable=False),
        sa.Column("score_semantics", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_query_tokens > 0 AND max_document_tokens > 0 AND max_pair_tokens > 0",
            name=op.f("ck_policy_reranker_profiles_token_limits_positive"),
        ),
        sa.CheckConstraint(
            "max_query_tokens + max_document_tokens <= max_pair_tokens",
            name=op.f("ck_policy_reranker_profiles_token_budgets_fit"),
        ),
        sa.CheckConstraint(
            "candidate_k > 0 AND candidate_k <= 50 AND final_k > 0 AND final_k <= candidate_k",
            name=op.f("ck_policy_reranker_profiles_ranking_limits_valid"),
        ),
        sa.CheckConstraint(
            "batch_size > 0 AND batch_size <= 50",
            name=op.f("ck_policy_reranker_profiles_batch_size_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_reranker_profiles")),
        sa.UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_reranker_profiles_version"
        ),
    )
    op.create_table(
        "policy_retrieval_execution_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("base_index_version_id", sa.Uuid(), nullable=False),
        sa.Column("reranker_profile_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_mode", sa.String(32), nullable=False),
        sa.Column("candidate_k", sa.Integer(), nullable=False),
        sa.Column("final_k", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "candidate_mode = 'HYBRID_RRF'",
            name=op.f("ck_policy_retrieval_execution_profiles_candidate_mode_allowed"),
        ),
        sa.CheckConstraint(
            "candidate_k > 0 AND candidate_k <= 50 AND final_k > 0 AND final_k <= candidate_k",
            name=op.f("ck_policy_retrieval_execution_profiles_ranking_limits_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','RETIRED')",
            name=op.f("ck_policy_retrieval_execution_profiles_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["base_index_version_id"],
            ["policy_index_versions.id"],
            name="fk_policy_retrieval_execution_profiles_base_index",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reranker_profile_id"],
            ["policy_reranker_profiles.id"],
            name="fk_policy_retrieval_execution_profiles_reranker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_execution_profiles")),
        sa.UniqueConstraint(
            "base_index_version_id",
            "profile_name",
            "profile_version",
            name="uq_policy_retrieval_execution_profiles_version",
        ),
    )
    op.create_index(
        "uq_policy_retrieval_execution_profiles_one_active",
        "policy_retrieval_execution_profiles",
        ["base_index_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_policy_retrieval_execution_profiles_one_active",
        table_name="policy_retrieval_execution_profiles",
    )
    op.drop_table("policy_retrieval_execution_profiles")
    op.drop_table("policy_reranker_profiles")
