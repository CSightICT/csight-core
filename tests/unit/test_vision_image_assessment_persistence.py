"""Contracts for immutable image-level any-defect persistence."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.adapters.persistence.analysis_repositories import (
    image_assessment_model_from_entity,
    vision_result_entity_from_models,
    vision_result_model_from_entity,
)
from app.adapters.persistence.base import Base
from app.platform.analysis import (
    ImageQualityResult,
    ImageUsability,
    VisionAnalysisResult,
    VisionAnalysisResultRecord,
    VisionImageAssessment,
    VisionImageAssessmentOutcome,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def _record() -> VisionAnalysisResultRecord:
    return VisionAnalysisResultRecord(
        id=str(uuid4()),
        tenant_id=str(uuid4()),
        analysis_run_id=str(uuid4()),
        stage_run_id=str(uuid4()),
        evidence_id=str(uuid4()),
        result=VisionAnalysisResult(
            provider_name="remote_vision",
            model_name="dinov2-any-defect",
            model_version="e3-epoch-10",
            model_revision="checkpoint-package-revision",
            dataset_version="kaputt-heldout-report-2026-08-27",
            taxonomy_version="csight-any-defect-assessment-v1",
            threshold_version="e3-validation-frozen-v1",
            preprocess_version="full-frame-1024-v1",
            postprocess_version="sigmoid-any-defect-v1",
            image_width=1024,
            image_height=1024,
            image_quality=ImageQualityResult(usable=ImageUsability.NOT_EVALUATED),
            image_assessment=VisionImageAssessment(
                score=0.95,
                threshold=0.8984375,
                outcome=VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE,
            ),
            latency_ms=37,
        ),
        created_at=NOW,
    )


def test_image_assessment_round_trips_without_detection_geometry_or_type() -> None:
    record = _record()
    result_model = vision_result_model_from_entity(record)
    assessment = record.result.image_assessment
    assert assessment is not None
    assessment_model = image_assessment_model_from_entity(
        tenant_id=record.tenant_id,
        vision_result_id=record.id,
        assessment_id=str(uuid4()),
        assessment=assessment,
        created_at=record.created_at,
    )

    restored = vision_result_entity_from_models(result_model, (), assessment_model)

    assert restored == record
    assert restored.result.detections == ()
    assert restored.result.image_assessment == assessment


def test_image_assessment_table_is_one_to_one_tenant_scoped_and_fail_closed() -> None:
    table = Base.metadata.tables["vision_image_assessments"]
    foreign_keys = {
        str(item.name): tuple(element.target_fullname for element in item.elements)
        for item in table.constraints
        if isinstance(item, ForeignKeyConstraint)
    }
    uniques = {
        str(item.name): tuple(column.name for column in item.columns)
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
    }
    checks = {
        str(item.name): str(item.sqltext)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    }

    assert foreign_keys["fk_vision_image_assessments_tenant_result_vision_results"] == (
        "vision_analysis_results.tenant_id",
        "vision_analysis_results.id",
    )
    assert uniques["uq_vision_image_assessments_tenant_result"] == (
        "tenant_id",
        "vision_result_id",
    )
    assert "score >= threshold" in checks["ck_vision_image_assessments_outcome_matches_threshold"]
    assert all(len(name) <= 63 for name in (*foreign_keys, *uniques, *checks))
