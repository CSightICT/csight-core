"""Add multimodal evidence snapshots and append-only Vision results.

Revision ID: 20260826_0004
Revises: 20260826_0003
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0004"
down_revision: str | None = "20260826_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_analysis_runs_pipeline_name_allowed"), "analysis_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_pipeline_name_allowed"),
        "analysis_runs",
        "pipeline_name IN ('product_defect_text_extraction', 'product_defect_multimodal_analysis')",
    )
    op.drop_constraint(op.f("ck_analysis_runs_status_allowed"), "analysis_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_analysis_runs_status_allowed"),
        "analysis_runs",
        "status IN ('QUEUED','RUNNING','RETRY_WAITING','PARTIAL_SUCCESS','SUCCEEDED','FAILED')",
    )
    op.drop_constraint(
        op.f("ck_analysis_runs_status_timestamps_consistent"), "analysis_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_status_timestamps_consistent"),
        "analysis_runs",
        "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
        "(status IN ('RUNNING', 'RETRY_WAITING') AND started_at IS NOT NULL "
        "AND completed_at IS NULL) OR "
        "(status IN ('PARTIAL_SUCCESS', 'SUCCEEDED', 'FAILED') AND started_at IS NOT NULL "
        "AND completed_at IS NOT NULL)",
    )

    op.create_table(
        "analysis_run_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_analysis_run_evidence_position_nonnegative")
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_analysis_run_evidence_sha256_lower_hex"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_analysis_run_evidence_tenant_run_analysis_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "evidence_id"),
            ("case_evidence.tenant_id", "case_evidence.id"),
            name=op.f("fk_analysis_run_evidence_tenant_evidence_case_evidence"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_run_evidence")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_analysis_run_evidence_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "evidence_id",
            name=op.f("uq_analysis_run_evidence_item"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "position",
            name=op.f("uq_analysis_run_evidence_position"),
        ),
    )
    op.create_index(
        "ix_analysis_run_evidence_tenant_run_position",
        "analysis_run_evidence",
        ["tenant_id", "analysis_run_id", "position"],
    )

    op.create_table(
        "vision_analysis_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage_type",
            sa.String(length=64),
            server_default=sa.text("'VISION_ANALYSIS'"),
            nullable=False,
        ),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=True),
        sa.Column("dataset_version", sa.String(length=100), nullable=True),
        sa.Column("taxonomy_version", sa.String(length=100), nullable=False),
        sa.Column("threshold_version", sa.String(length=100), nullable=False),
        sa.Column("preprocess_version", sa.String(length=100), nullable=False),
        sa.Column("postprocess_version", sa.String(length=100), nullable=False),
        sa.Column("framework", sa.String(length=100), nullable=True),
        sa.Column("runtime", sa.String(length=100), nullable=True),
        sa.Column("precision", sa.String(length=100), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("image_quality", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage_type = 'VISION_ANALYSIS'",
            name=op.f("ck_vision_analysis_results_stage_type_vision_analysis"),
        ),
        sa.CheckConstraint(
            "image_width > 0 AND image_height > 0",
            name=op.f("ck_vision_analysis_results_image_dimensions_positive"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name=op.f("ck_vision_analysis_results_latency_nonnegative"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(image_quality) = 'object'",
            name=op.f("ck_vision_analysis_results_image_quality_object"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("analysis_runs.tenant_id", "analysis_runs.id"),
            name=op.f("fk_vision_results_tenant_run_analysis_runs"),
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
            name=op.f("fk_vision_results_tenant_run_stage_type_stage_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "evidence_id"),
            ("case_evidence.tenant_id", "case_evidence.id"),
            name=op.f("fk_vision_results_tenant_evidence_case_evidence"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_analysis_results")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_vision_results_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "evidence_id",
            name=op.f("uq_vision_results_tenant_run_evidence"),
        ),
    )
    op.create_index(
        "ix_vision_results_tenant_run_created",
        "vision_analysis_results",
        ["tenant_id", "analysis_run_id", "created_at", "id"],
    )

    op.create_table(
        "vision_detections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vision_result_id", sa.Uuid(), nullable=False),
        sa.Column("detection_index", sa.Integer(), nullable=False),
        sa.Column("detection_id", sa.String(length=100), nullable=False),
        sa.Column("canonical_label", sa.String(length=64), nullable=False),
        sa.Column("model_class_id", sa.String(length=100), nullable=True),
        sa.Column("model_class_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("geometry_type", sa.String(length=32), nullable=False),
        sa.Column("coordinate_system", sa.String(length=32), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "detection_index >= 0",
            name=op.f("ck_vision_detections_detection_index_nonnegative"),
        ),
        sa.CheckConstraint(
            "canonical_label IN ('LEAKAGE','CONTAINER_DAMAGE','DENT','CRACK','SCRATCH',"
            "'DISCOLORATION','MISSING_PART','BREAKAGE','MISSING_COMPONENT',"
            "'FUNCTIONAL_FAILURE','PACKAGING_DAMAGE','CONTAMINATION','SURFACE_DAMAGE',"
            "'OTHER','UNKNOWN')",
            name=op.f("ck_vision_detections_canonical_label_allowed"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name=op.f("ck_vision_detections_confidence_range"),
        ),
        sa.CheckConstraint(
            "geometry_type = 'BOUNDING_BOX'",
            name=op.f("ck_vision_detections_geometry_type_bbox"),
        ),
        sa.CheckConstraint(
            "coordinate_system = 'normalized_xyxy'",
            name=op.f("ck_vision_detections_coordinate_system_normalized"),
        ),
        sa.CheckConstraint(
            "x1 >= 0 AND x1 < x2 AND x2 <= 1",
            name=op.f("ck_vision_detections_x_coordinates_ordered"),
        ),
        sa.CheckConstraint(
            "y1 >= 0 AND y1 < y2 AND y2 <= 1",
            name=op.f("ck_vision_detections_y_coordinates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "vision_result_id"),
            ("vision_analysis_results.tenant_id", "vision_analysis_results.id"),
            name=op.f("fk_vision_detections_tenant_result_vision_results"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vision_detections")),
        sa.UniqueConstraint(
            "tenant_id",
            "vision_result_id",
            "detection_index",
            name=op.f("uq_vision_detection_index"),
        ),
    )
    op.create_index(
        "ix_vision_detections_tenant_result_index",
        "vision_detections",
        ["tenant_id", "vision_result_id", "detection_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_vision_detections_tenant_result_index", table_name="vision_detections")
    op.drop_table("vision_detections")
    op.drop_index("ix_vision_results_tenant_run_created", table_name="vision_analysis_results")
    op.drop_table("vision_analysis_results")
    op.drop_index(
        "ix_analysis_run_evidence_tenant_run_position", table_name="analysis_run_evidence"
    )
    op.drop_table("analysis_run_evidence")
    op.drop_constraint(
        op.f("ck_analysis_runs_status_timestamps_consistent"),
        "analysis_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_status_timestamps_consistent"),
        "analysis_runs",
        "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
        "(status IN ('RUNNING', 'RETRY_WAITING') AND started_at IS NOT NULL "
        "AND completed_at IS NULL) OR "
        "(status IN ('SUCCEEDED', 'FAILED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
    )
    op.drop_constraint(op.f("ck_analysis_runs_status_allowed"), "analysis_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_analysis_runs_status_allowed"),
        "analysis_runs",
        "status IN ('QUEUED','RUNNING','RETRY_WAITING','SUCCEEDED','FAILED')",
    )
    op.drop_constraint(
        op.f("ck_analysis_runs_pipeline_name_allowed"), "analysis_runs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_analysis_runs_pipeline_name_allowed"),
        "analysis_runs",
        "pipeline_name = 'product_defect_text_extraction'",
    )
