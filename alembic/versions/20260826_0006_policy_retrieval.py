"""Persist versioned policy corpus and exact hybrid retrieval artifacts.

Revision ID: 20260826_0006
Revises: 20260826_0005
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0006"
down_revision: str | None = "20260826_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "policy_ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("corpus_name", sa.String(255), nullable=False),
        sa.Column("corpus_version", sa.String(64), nullable=False),
        sa.Column("corpus_source_hash", sa.String(64), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_document_count", sa.Integer(), nullable=False),
        sa.Column("ingested_document_count", sa.Integer(), nullable=False),
        sa.Column("expected_clause_count", sa.Integer(), nullable=False),
        sa.Column("ingested_clause_count", sa.Integer(), nullable=False),
        sa.Column("builder_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_message", sa.String(1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')",
            name=op.f("ck_policy_ingestion_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "expected_document_count >= 0",
            name=op.f("ck_policy_ingestion_runs_expected_documents_nonnegative"),
        ),
        sa.CheckConstraint(
            "ingested_document_count >= 0",
            name=op.f("ck_policy_ingestion_runs_ingested_documents_nonnegative"),
        ),
        sa.CheckConstraint(
            "expected_clause_count >= 0",
            name=op.f("ck_policy_ingestion_runs_expected_clauses_nonnegative"),
        ),
        sa.CheckConstraint(
            "ingested_clause_count >= 0",
            name=op.f("ck_policy_ingestion_runs_ingested_clauses_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_ingestion_runs")),
    )
    op.create_index(
        "uq_policy_ingestion_runs_succeeded_identity",
        "policy_ingestion_runs",
        ["corpus_source_hash", "manifest_hash", "builder_version"],
        unique=True,
        postgresql_where=sa.text("status = 'SUCCEEDED'"),
    )

    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("policy_type", sa.String(128), nullable=False),
        sa.Column("authority_level", sa.String(128), nullable=False),
        sa.Column("product_categories", postgresql.ARRAY(sa.String(128)), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("document_status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("supersedes_document_id", sa.String(255), nullable=True),
        sa.Column("supersedes_document_version", sa.String(64), nullable=True),
        sa.Column("superseded_by_document_id", sa.String(255), nullable=True),
        sa.Column("superseded_by_document_version", sa.String(64), nullable=True),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "document_status IN ('ACTIVE','RETIRED')",
            name=op.f("ck_policy_documents_status_allowed"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_policy_documents_dates_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_policy_documents_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["policy_ingestion_runs.id"],
            name="fk_policy_documents_ingestion_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_documents")),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "document_version", name="uq_policy_documents_version"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_documents_tenant_id"),
    )
    op.create_index(
        "ix_policy_documents_tenant_effective_status",
        "policy_documents",
        ["tenant_id", "document_status", "effective_from", "effective_to"],
    )

    op.create_table(
        "policy_clauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_row_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("clause_id", sa.String(320), nullable=False),
        sa.Column("section_path", postgresql.ARRAY(sa.String(500)), nullable=False),
        sa.Column("clause_type", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parent_clause_id", sa.String(320), nullable=True),
        sa.Column("policy_type", sa.String(128), nullable=False),
        sa.Column("product_categories", postgresql.ARRAY(sa.String(128)), nullable=False),
        sa.Column("defect_types", postgresql.ARRAY(sa.String(128)), nullable=False),
        sa.Column("actions", postgresql.ARRAY(sa.String(128)), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("document_status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "clause_type IN ('RULE','EXCEPTION','EVIDENCE_REQUIREMENT','ESCALATION','DEFINITION','PROCEDURE')",
            name=op.f("ck_policy_clauses_type_allowed"),
        ),
        sa.CheckConstraint(
            "document_status IN ('ACTIVE','RETIRED')", name=op.f("ck_policy_clauses_status_allowed")
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_policy_clauses_dates_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_policy_clauses_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_row_id"],
            ["policy_documents.tenant_id", "policy_documents.id"],
            name="fk_policy_clauses_tenant_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["policy_ingestion_runs.id"],
            name="fk_policy_clauses_ingestion_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_clauses")),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "document_version",
            "clause_id",
            name="uq_policy_clauses_version_clause",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_policy_clauses_tenant_id"),
    )
    op.create_index(
        "ix_policy_clauses_tenant_effective_status",
        "policy_clauses",
        ["tenant_id", "document_status", "effective_from", "effective_to"],
    )
    op.create_index(
        "ix_policy_clauses_tenant_policy_type", "policy_clauses", ["tenant_id", "policy_type"]
    )
    op.create_index(
        "ix_policy_clauses_categories_gin",
        "policy_clauses",
        ["product_categories"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_policy_clauses_defects_gin", "policy_clauses", ["defect_types"], postgresql_using="gin"
    )
    op.create_index(
        "ix_policy_clauses_actions_gin", "policy_clauses", ["actions"], postgresql_using="gin"
    )

    op.create_table(
        "policy_embedding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("model_artifact", sa.String(255), nullable=False),
        sa.Column("model_revision", sa.String(255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("pooling_strategy", sa.String(128), nullable=False),
        sa.Column("normalize_embeddings", sa.Boolean(), nullable=False),
        sa.Column("query_instruction", sa.Text(), nullable=False),
        sa.Column("query_instruction_hash", sa.String(64), nullable=False),
        sa.Column("document_template_name", sa.String(128), nullable=False),
        sa.Column("document_template_version", sa.String(64), nullable=False),
        sa.Column("document_template_hash", sa.String(64), nullable=False),
        sa.Column("max_query_tokens", sa.Integer(), nullable=False),
        sa.Column("max_document_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0", name=op.f("ck_policy_embedding_profiles_dimension_positive")
        ),
        sa.CheckConstraint(
            "max_query_tokens > 0", name=op.f("ck_policy_embedding_profiles_query_tokens_positive")
        ),
        sa.CheckConstraint(
            "max_document_tokens > 0",
            name=op.f("ck_policy_embedding_profiles_document_tokens_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_embedding_profiles")),
        sa.UniqueConstraint(
            "profile_name", "profile_version", name="uq_policy_embedding_profiles_version"
        ),
    )

    op.create_table(
        "policy_clause_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("document_text_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0", name=op.f("ck_policy_clause_embeddings_dimension_positive")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_policy_clause_embeddings_tenant_clause",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_profile_id"],
            ["policy_embedding_profiles.id"],
            name="fk_policy_clause_embeddings_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_clause_embeddings")),
        sa.UniqueConstraint(
            "policy_clause_row_id",
            "embedding_profile_id",
            name="uq_policy_clause_embeddings_clause_profile",
        ),
    )

    op.create_table(
        "policy_index_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("index_name", sa.String(128), nullable=False),
        sa.Column("index_version", sa.String(64), nullable=False),
        sa.Column("corpus_name", sa.String(255), nullable=False),
        sa.Column("corpus_version", sa.String(64), nullable=False),
        sa.Column("corpus_source_hash", sa.String(64), nullable=False),
        sa.Column("lexical_profile_name", sa.String(128), nullable=False),
        sa.Column("lexical_profile_version", sa.String(64), nullable=False),
        sa.Column("lexical_k1", sa.Float(), nullable=False),
        sa.Column("lexical_b", sa.Float(), nullable=False),
        sa.Column("embedding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("fusion_profile_name", sa.String(128), nullable=False),
        sa.Column("fusion_profile_version", sa.String(64), nullable=False),
        sa.Column("fusion_rrf_k", sa.Integer(), nullable=False),
        sa.Column("fusion_lexical_weight", sa.Float(), nullable=False),
        sa.Column("fusion_dense_weight", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expected_clause_count", sa.Integer(), nullable=False),
        sa.Column("indexed_clause_count", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('BUILDING','ACTIVE','FAILED','RETIRED')",
            name=op.f("ck_policy_index_versions_status_allowed"),
        ),
        sa.CheckConstraint(
            "expected_clause_count >= 0",
            name=op.f("ck_policy_index_versions_expected_clauses_nonnegative"),
        ),
        sa.CheckConstraint(
            "indexed_clause_count >= 0",
            name=op.f("ck_policy_index_versions_indexed_clauses_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_policy_index_versions_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["embedding_profile_id"],
            ["policy_embedding_profiles.id"],
            name="fk_policy_index_versions_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_index_versions")),
        sa.UniqueConstraint(
            "tenant_id", "index_name", "index_version", name="uq_policy_index_versions_version"
        ),
    )
    op.create_index(
        "uq_policy_index_versions_one_active",
        "policy_index_versions",
        ["tenant_id", "index_name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_policy_index_versions_one_active", table_name="policy_index_versions")
    op.drop_table("policy_index_versions")
    op.drop_table("policy_clause_embeddings")
    op.drop_table("policy_embedding_profiles")
    op.drop_index("ix_policy_clauses_actions_gin", table_name="policy_clauses")
    op.drop_index("ix_policy_clauses_defects_gin", table_name="policy_clauses")
    op.drop_index("ix_policy_clauses_categories_gin", table_name="policy_clauses")
    op.drop_index("ix_policy_clauses_tenant_policy_type", table_name="policy_clauses")
    op.drop_index("ix_policy_clauses_tenant_effective_status", table_name="policy_clauses")
    op.drop_table("policy_clauses")
    op.drop_index("ix_policy_documents_tenant_effective_status", table_name="policy_documents")
    op.drop_table("policy_documents")
    op.drop_index("uq_policy_ingestion_runs_succeeded_identity", table_name="policy_ingestion_runs")
    op.drop_table("policy_ingestion_runs")
