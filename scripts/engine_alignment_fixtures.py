"""Synthetic canonical-output fixtures, not images, model predictions or Human Gold."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from app.domains.product_defect_cs.evidence_alignment import (
    AlignmentInput,
    AlignmentProfile,
    AlignmentStatus,
    Contract,
    Reason,
    TextSource,
    VisionSource,
)
from app.platform.analysis.enums import (
    DefectLocation,
    DefectType,
    ExtractionIssueType,
    ImageUsability,
    VisionImageAssessmentOutcome,
)
from app.platform.analysis.llm_v2 import (
    ActionConsistency,
    CompletenessResult,
    LLMExtractionResultV2Record,
    LLMTextClaimV2,
    LLMTextExtractionRequestV2,
    LLMTextExtractionResultV2,
)
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.analysis.schemas import (
    AnalysisEvidenceSnapshot,
    BoundingBox,
    DetectionFinding,
    ImageQualityResult,
    VisionAnalysisResult,
    VisionAnalysisResultRecord,
    VisionImageAssessment,
)


class FixtureImage(Contract):
    label: DefectType | None = None
    confidence: float = Field(default=0.9, ge=0, le=1, allow_inf_nan=False)
    quality: ImageUsability = ImageUsability.USABLE
    missing: bool = False
    revision_missing: bool = False
    binary_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    blurred: bool | None = None
    product_visible: bool | None = None


class ContractCase(Contract):
    id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    split: Literal["DEV_CONTRACT"] = "DEV_CONTRACT"
    claims: tuple[ExtractionIssueType, ...] = Field(min_length=1, max_length=10)
    location: DefectLocation = DefectLocation.UNKNOWN
    images: tuple[FixtureImage, ...] = Field(max_length=20)
    text_revision_missing: bool = False
    expected: tuple[AlignmentStatus, ...]
    required_reasons: tuple[Reason, ...] = ()


def make_input(case: ContractCase) -> AlignmentInput:
    """Convert explicitly synthetic observations into the real canonical contracts."""
    stamp = datetime(2026, 9, 9, tzinfo=UTC)
    request = LLMTextExtractionRequestV2(customer_message="합성 문의의 명시적 주장입니다.")
    result = LLMTextExtractionResultV2(
        issue_types=tuple(dict.fromkeys(case.claims)),
        claims=tuple(
            LLMTextClaimV2(
                type=issue,
                location=case.location,
                description="합성 구조 테스트",
                source_quote="명시적 주장",
            )
            for issue in case.claims
        ),
        summary="합성 구조 테스트",
    )
    snapshots: list[AnalysisEvidenceSnapshot] = []
    vision: list[VisionSource] = []
    for index, image in enumerate(case.images):
        evidence_id = f"synthetic-evidence-{index}"
        digest = f"{index + 1:064x}"
        snapshots.append(
            AnalysisEvidenceSnapshot(
                id=f"snapshot-{index}",
                tenant_id="synthetic-tenant",
                analysis_run_id=case.id,
                evidence_id=evidence_id,
                position=index,
                sha256=digest,
                created_at=stamp,
            )
        )
        if image.missing:
            continue
        binary = None
        if image.binary_score is not None:
            binary = VisionImageAssessment(
                score=image.binary_score,
                threshold=0.8,
                outcome=(
                    VisionImageAssessmentOutcome.HIGH_CONFIDENCE_DEFECT_CANDIDATE
                    if image.binary_score >= 0.8
                    else VisionImageAssessmentOutcome.BELOW_HIGH_CONFIDENCE_THRESHOLD
                ),
            )
        detections = (
            ()
            if image.label is None
            else (
                DetectionFinding(
                    id="detection-0",
                    label=image.label,
                    confidence=image.confidence,
                    geometry=BoundingBox(x1=0.1, y1=0.1, x2=0.6, y2=0.6),
                ),
            )
        )
        vision_result = VisionAnalysisResult(
            provider_name="synthetic",
            model_name="synthetic-vision",
            model_version="fixture-v1",
            model_revision=None if image.revision_missing else "synthetic-vision-revision",
            dataset_version="alignment-contract-v1",
            taxonomy_version="fixture-v1",
            threshold_version="fixture-v1",
            preprocess_version="fixture-v1",
            postprocess_version="fixture-v1",
            image_width=100,
            image_height=100,
            image_reference=evidence_id,
            image_quality=ImageQualityResult(
                usable=image.quality,
                blurred=image.blurred,
                product_visible=image.product_visible,
            ),
            detections=detections,
            image_assessment=binary,
            latency_ms=0,
        )
        vision.append(
            VisionSource(
                record=VisionAnalysisResultRecord(
                    id=f"vision-result-{index}",
                    tenant_id="synthetic-tenant",
                    analysis_run_id=case.id,
                    stage_run_id="vision-stage",
                    evidence_id=evidence_id,
                    result=vision_result,
                    created_at=stamp,
                ),
                evidence_sha256=digest,
                artifact_sha256="b" * 64,
                runtime_sha256="c" * 64,
            )
        )
    return AlignmentInput(
        source_scope="SYNTHETIC_FIXTURE",
        tenant_id="synthetic-tenant",
        analysis_run_id=case.id,
        profile=AlignmentProfile(detection_min_score=0.8, threshold_basis="SYNTHETIC_CONTRACT"),
        text=TextSource(
            request=request,
            record=LLMExtractionResultV2Record(
                id="text-result",
                tenant_id="synthetic-tenant",
                analysis_run_id=case.id,
                stage_run_id="text-stage",
                result=result,
                created_at=stamp,
                completeness=CompletenessResult(
                    system_missing_information=(),
                    action_consistency=ActionConsistency.BOTH_UNSPECIFIED,
                ),
            ),
            metadata=ProviderExecutionMetadata(
                provider_name="synthetic",
                model_name="synthetic-text",
                model_version="fixture-v1",
                model_revision=None if case.text_revision_missing else "synthetic-text-revision",
                latency_ms=0,
            ),
            artifact_sha256="a" * 64,
            runtime_sha256="c" * 64,
            prompt_name="synthetic-extraction",
            prompt_version="fixture-v1",
            prompt_sha256="d" * 64,
        ),
        snapshots=tuple(snapshots),
        vision=tuple(vision),
    )
