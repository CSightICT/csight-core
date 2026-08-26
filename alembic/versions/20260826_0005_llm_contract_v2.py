"""Add append-only LLM extraction contract v2 child results.

Revision ID: 20260826_0005
Revises: 20260826_0004
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0005"
down_revision: str | None = "20260826_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_analysis_runs_pipeline_version_allowed"), "analysis_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_pipeline_version_allowed"),
        "analysis_runs",
        "pipeline_version IN ('1.0.0', '2.0.0')",
    )
    op.create_table(
        "llm_extraction_results_v2",
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
        sa.Column("requested_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("text_ambiguities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "system_missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("action_consistency", sa.String(length=64), nullable=False),
        sa.Column("completeness_rule_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage_type = 'TEXT_EXTRACTION'",
            name=op.f("ck_llm_extraction_results_v2_stage_type_text_extraction"),
        ),
        sa.CheckConstraint(
            "schema_version = '2.0'", name=op.f("ck_llm_extraction_results_v2_schema_version_v2")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(issue_types) = 'array'",
            name=op.f("ck_llm_extraction_results_v2_issue_types_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(claims) = 'array'", name=op.f("ck_llm_extraction_results_v2_claims_array")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(requested_actions) = 'array'",
            name=op.f("ck_llm_extraction_results_v2_actions_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(text_ambiguities) = 'array'",
            name=op.f("ck_llm_extraction_results_v2_ambiguities_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(system_missing_information) = 'array'",
            name=op.f("ck_llm_extraction_results_v2_missing_array"),
        ),
        sa.CheckConstraint(
            "action_consistency IN ('MATCH','MISMATCH','ONLY_DECLARED','ONLY_EXTRACTED',"
            "'BOTH_UNSPECIFIED','MULTIPLE_EXTRACTED','NOT_COMPARABLE')",
            name=op.f("ck_llm_extraction_results_v2_action_consistency_allowed"),
        ),
        sa.CheckConstraint(
            "completeness_rule_version = '1.0.0'",
            name=op.f("ck_llm_extraction_results_v2_rule_version_v1"),
        ),
        sa.CheckConstraint(
            "length(btrim(summary)) > 0", name=op.f("ck_llm_extraction_results_v2_summary_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_llm_results_v2_tenant_run_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id", "stage_run_id", "stage_type"),
            (
                "analysis_stage_runs.tenant_id",
                "analysis_stage_runs.analysis_run_id",
                "analysis_stage_runs.id",
                "analysis_stage_runs.stage_type",
            ),
            name=op.f("fk_llm_results_v2_tenant_run_stage_type_stage_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_extraction_results_v2")),
        sa.UniqueConstraint(
            "tenant_id", "analysis_run_id", name=op.f("uq_llm_results_v2_tenant_run")
        ),
        sa.UniqueConstraint(
            "tenant_id", "stage_run_id", name=op.f("uq_llm_results_v2_tenant_stage")
        ),
    )
    op.create_index(
        "ix_llm_results_v2_tenant_run",
        "llm_extraction_results_v2",
        ["tenant_id", "analysis_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_results_v2_tenant_run", table_name="llm_extraction_results_v2")
    op.drop_table("llm_extraction_results_v2")
    op.drop_constraint(
        op.f("ck_analysis_runs_pipeline_version_allowed"), "analysis_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_pipeline_version_allowed"),
        "analysis_runs",
        "pipeline_version = '1.0.0'",
    )
