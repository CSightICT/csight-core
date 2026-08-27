"""Add append-only image-level any-defect assessments.

Revision ID: 20260827_0015_vision_image_assessment
Revises: 20260827_0014_review_report_poc_metrics
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0015_vision_image_assessment"
down_revision: str | None = "20260827_0014_review_report_poc_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vision_image_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vision_result_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type", sa.String(length=32), nullable=False),
        sa.Column("model_output_name", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("threshold_operator", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assessment_type = 'ANY_DEFECT'",
            name=op.f("ck_vision_image_assessments_type_any_defect"),
        ),
        sa.CheckConstraint(
            "model_output_name = 'defect'",
            name=op.f("ck_vision_image_assessments_output_name_defect"),
        ),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 1",
            name=op.f("ck_vision_image_assessments_score_range"),
        ),
        sa.CheckConstraint(
            "threshold BETWEEN 0 AND 1",
            name=op.f("ck_vision_image_assessments_threshold_range"),
        ),
        sa.CheckConstraint(
            "threshold_operator = 'GREATER_THAN_OR_EQUAL'",
            name=op.f("ck_vision_image_assessments_threshold_operator_supported"),
        ),
        sa.CheckConstraint(
            "outcome IN ('HIGH_CONFIDENCE_DEFECT_CANDIDATE','BELOW_HIGH_CONFIDENCE_THRESHOLD')",
            name=op.f("ck_vision_image_assessments_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "(score >= threshold AND outcome = 'HIGH_CONFIDENCE_DEFECT_CANDIDATE') OR "
            "(score < threshold AND outcome = 'BELOW_HIGH_CONFIDENCE_THRESHOLD')",
            name=op.f("ck_vision_image_assessments_outcome_matches_threshold"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "vision_result_id"),
            ("vision_analysis_results.tenant_id", "vision_analysis_results.id"),
            name=op.f("fk_vision_image_assessments_tenant_result_vision_results"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_image_assessments")),
        sa.UniqueConstraint(
            "tenant_id",
            "vision_result_id",
            name=op.f("uq_vision_image_assessments_tenant_result"),
        ),
    )


def downgrade() -> None:
    op.drop_table("vision_image_assessments")
