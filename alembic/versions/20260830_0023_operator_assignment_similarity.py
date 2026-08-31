"""Add admin assignment actions and append-only policy similarity evidence.

Revision ID: 20260830_0023_operator_assignment_similarity
Revises: 20260829_0022_privacy_lifecycle
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260830_0023_operator_assignment_similarity"
down_revision: str | None = "20260829_0022_privacy_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_EXPRESSION = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_human_review_actions_type_allowed"),
        "human_review_actions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_human_review_actions_type_allowed"),
        "human_review_actions",
        "action_type IN ('CREATED','ASSIGNED','REASSIGNED','CLAIMED','RELEASED',"
        "'EVIDENCE_REQUESTED','RESUMED','ESCALATED','RESOLVED')",
    )

    op.create_table(
        "policy_retrieval_similarity_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=False),
        sa.Column("similarity_group", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("cosine_similarity", sa.Float(), nullable=False),
        sa.Column("reference_threshold", sa.Float(), nullable=False),
        sa.Column("threshold_version", sa.String(128), nullable=False),
        sa.Column("matched_query_ids", postgresql.JSONB(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "retrieval_run_id"],
            ["policy_retrieval_runs.tenant_id", "policy_retrieval_runs.id"],
            name="fk_policy_retrieval_similarity_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_policy_retrieval_similarity_clause",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "similarity_group IN ('NEAREST','LEAST')",
            name=op.f("ck_policy_retrieval_similarity_evidence_group_allowed"),
        ),
        sa.CheckConstraint(
            "rank BETWEEN 1 AND 3",
            name=op.f("ck_policy_retrieval_similarity_evidence_rank_valid"),
        ),
        sa.CheckConstraint(
            "cosine_similarity BETWEEN -1.0 AND 1.0",
            name=op.f("ck_policy_retrieval_similarity_evidence_cosine_similarity_valid"),
        ),
        sa.CheckConstraint(
            "reference_threshold BETWEEN -1.0 AND 1.0",
            name=op.f("ck_policy_retrieval_similarity_evidence_reference_value_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_retrieval_similarity_evidence")),
        sa.UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "similarity_group",
            "rank",
            name="uq_policy_retrieval_similarity_rank",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "retrieval_run_id",
            "similarity_group",
            "policy_clause_row_id",
            name="uq_policy_retrieval_similarity_clause",
        ),
    )
    op.create_index(
        "ix_policy_retrieval_similarity_run_group",
        "policy_retrieval_similarity_evidence",
        ["tenant_id", "retrieval_run_id", "similarity_group", "rank"],
    )
    op.execute("ALTER TABLE policy_retrieval_similarity_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE policy_retrieval_similarity_evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY csight_tenant_scope ON policy_retrieval_similarity_evidence
        FOR ALL TO csight_api_role, csight_worker_role
        USING ({_TENANT_EXPRESSION})
        WITH CHECK ({_TENANT_EXPRESSION})
        """
    )
    op.execute(
        "GRANT SELECT, INSERT ON policy_retrieval_similarity_evidence "
        "TO csight_api_role, csight_worker_role"
    )
    op.execute(
        "REVOKE UPDATE, DELETE ON policy_retrieval_similarity_evidence "
        "FROM csight_api_role, csight_worker_role, csight_dispatcher_role"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_policy_retrieval_similarity_run_group",
        table_name="policy_retrieval_similarity_evidence",
    )
    op.drop_table("policy_retrieval_similarity_evidence")
    op.drop_constraint(
        op.f("ck_human_review_actions_type_allowed"),
        "human_review_actions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_human_review_actions_type_allowed"),
        "human_review_actions",
        "action_type IN ('CREATED','CLAIMED','RELEASED','EVIDENCE_REQUESTED',"
        "'RESUMED','ESCALATED','RESOLVED')",
    )
