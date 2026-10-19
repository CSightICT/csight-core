"""Decision-free, deterministic replay of text claims against canonical Vision results."""

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.analysis.enums import DefectLocation, ExtractionIssueType, ImageUsability
from app.platform.analysis.llm_v2 import LLMExtractionResultV2Record, LLMTextExtractionRequestV2
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.analysis.schemas import AnalysisEvidenceSnapshot, VisionAnalysisResultRecord

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Reference = Annotated[str, Field(min_length=1, max_length=255)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AlignmentStatus(StrEnum):
    TYPE_CANDIDATE = "TYPE_CANDIDATE"
    UNRESOLVED = "UNRESOLVED"


class Reason(StrEnum):
    TYPE_MATCH_ONLY = "TYPE_MATCH_ONLY"
    CLAIM_LOCATION_UNVERIFIED = "CLAIM_LOCATION_UNVERIFIED"
    NON_VISUAL_CLAIM = "NON_VISUAL_CLAIM"
    REFERENCE_OR_SEMANTIC_EVIDENCE_REQUIRED = "REFERENCE_OR_SEMANTIC_EVIDENCE_REQUIRED"
    NO_IMAGE_EVIDENCE = "NO_IMAGE_EVIDENCE"
    VISION_RESULT_MISSING = "VISION_RESULT_MISSING"
    SOURCE_IDENTITY_INCOMPLETE = "SOURCE_IDENTITY_INCOMPLETE"
    IMAGE_QUALITY_NOT_EVALUATED = "IMAGE_QUALITY_NOT_EVALUATED"
    IMAGE_NOT_USABLE = "IMAGE_NOT_USABLE"
    IMAGE_LEVEL_ONLY = "IMAGE_LEVEL_ONLY"
    NO_TYPED_DETECTION = "NO_TYPED_DETECTION"
    DIFFERENT_TYPE_NOT_COUNTEREVIDENCE = "DIFFERENT_TYPE_NOT_COUNTEREVIDENCE"
    BELOW_PROFILE_THRESHOLD = "BELOW_PROFILE_THRESHOLD"


class EvidenceRequest(StrEnum):
    PROVIDE_IMAGE = "PROVIDE_IMAGE"
    RETAKE_CLEAR_PRODUCT_IMAGE = "RETAKE_CLEAR_PRODUCT_IMAGE"
    CHECK_IMAGE_QUALITY = "CHECK_IMAGE_QUALITY"
    COMPLETE_VISION_ANALYSIS = "COMPLETE_VISION_ANALYSIS"
    VERIFY_SOURCE_IDENTITY = "VERIFY_SOURCE_IDENTITY"
    REVIEW_CLAIMED_AREA = "REVIEW_CLAIMED_AREA"
    PROVIDE_REFERENCE_OR_DETAILS = "PROVIDE_REFERENCE_OR_DETAILS"
    PROVIDE_NON_VISUAL_EVIDENCE = "PROVIDE_NON_VISUAL_EVIDENCE"


class AlignmentProfile(Contract):
    version: Literal["claim_vision_alignment/1.0.0"] = "claim_vision_alignment/1.0.0"
    detection_min_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    threshold_basis: Literal["SYNTHETIC_CONTRACT", "UNQUALIFIED_EXPERIMENT"]


class TextSource(Contract):
    request: LLMTextExtractionRequestV2 = Field(repr=False)
    record: LLMExtractionResultV2Record = Field(repr=False)
    metadata: ProviderExecutionMetadata
    artifact_sha256: Digest
    runtime_sha256: Digest
    prompt_name: Reference
    prompt_version: Reference
    prompt_sha256: Digest


class VisionSource(Contract):
    record: VisionAnalysisResultRecord = Field(repr=False)
    evidence_sha256: Digest
    artifact_sha256: Digest
    runtime_sha256: Digest


class AlignmentInput(Contract):
    schema_version: Literal["alignment_input/1.0.0"] = "alignment_input/1.0.0"
    source_scope: Literal["SYNTHETIC_FIXTURE", "REAL_MODEL_DIAGNOSTIC"]
    tenant_id: Reference
    analysis_run_id: Reference
    profile: AlignmentProfile
    text: TextSource = Field(repr=False)
    snapshots: tuple[AnalysisEvidenceSnapshot, ...] = Field(default=(), max_length=20)
    vision: tuple[VisionSource, ...] = Field(default=(), max_length=20, repr=False)

    @model_validator(mode="after")
    def require_bound_sources(self) -> "AlignmentInput":
        scope = (self.tenant_id, self.analysis_run_id)
        text = self.text.record
        if (text.tenant_id, text.analysis_run_id) != scope:
            raise ValueError("ALIGNMENT_SCOPE_MISMATCH")
        result = text.result
        if {claim.type for claim in result.claims} != set(result.issue_types):
            raise ValueError("ALIGNMENT_CLAIM_TYPE_MISMATCH")
        result.require_exact_source_quotes(
            customer_message=self.text.request.customer_message,
            provider=self.text.metadata.provider_name,
        )
        snapshots = {item.evidence_id: item for item in self.snapshots}
        if (
            len(snapshots) != len(self.snapshots)
            or len({s.id for s in self.snapshots}) != len(self.snapshots)
            or {s.position for s in self.snapshots} != set(range(len(self.snapshots)))
        ):
            raise ValueError("ALIGNMENT_DUPLICATE_OR_INVALID_SNAPSHOT")
        for snapshot in self.snapshots:
            if (snapshot.tenant_id, snapshot.analysis_run_id) != scope:
                raise ValueError("ALIGNMENT_SCOPE_MISMATCH")
        seen_evidence: set[str] = set()
        seen_results: set[str] = set()
        stages: set[str] = set()
        vision_identities: set[tuple[str | None, ...]] = set()
        for source in self.vision:
            record = source.record
            if (record.tenant_id, record.analysis_run_id) != scope:
                raise ValueError("ALIGNMENT_SCOPE_MISMATCH")
            snapshot = snapshots.get(record.evidence_id)
            if snapshot is None or source.evidence_sha256 != snapshot.sha256:
                raise ValueError("ALIGNMENT_EVIDENCE_BINDING_MISMATCH")
            if record.evidence_id in seen_evidence or record.id in seen_results:
                raise ValueError("ALIGNMENT_DUPLICATE_RESULT")
            if record.result.model_dump()["image_reference"] not in (None, record.evidence_id):
                raise ValueError("ALIGNMENT_IMAGE_REFERENCE_MISMATCH")
            if len(record.result.detections) > 100:
                raise ValueError("ALIGNMENT_TOO_MANY_DETECTIONS")
            ids = [d.id for d in record.result.detections]
            if len(set(ids)) != len(ids):
                raise ValueError("ALIGNMENT_DUPLICATE_DETECTION")
            seen_evidence.add(record.evidence_id)
            seen_results.add(record.id)
            stages.add(record.stage_run_id)
            result = record.result
            vision_identities.add(
                (
                    result.provider_name,
                    result.model_name,
                    result.model_version,
                    result.model_revision,
                    result.taxonomy_version,
                    result.threshold_version,
                    result.preprocess_version,
                    result.postprocess_version,
                    result.dataset_version,
                    source.artifact_sha256,
                    source.runtime_sha256,
                )
            )
        if len(stages) > 1 or text.stage_run_id in stages:
            raise ValueError("ALIGNMENT_STAGE_MISMATCH")
        if len(vision_identities) > 1:
            raise ValueError("ALIGNMENT_MIXED_VISION_IDENTITY")
        return self


class CandidateLink(Contract):
    evidence_id: Reference
    vision_result_id: Reference
    detection_id: Reference
    evidence_sha256: Digest


class ClaimAlignment(Contract):
    claim_index: int = Field(ge=0)
    claim_type: ExtractionIssueType
    claimed_location: DefectLocation
    status: AlignmentStatus
    candidates: tuple[CandidateLink, ...]
    reasons: tuple[Reason, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    location_verified: Literal[False] = False


class SourceReference(Contract):
    result_id: Reference
    stage_run_id: Reference
    evidence_id: Reference | None = None
    evidence_sha256: Digest | None = None
    result_sha256: Digest
    result_schema_version: Reference
    provider: Reference
    model: Reference
    model_version: Reference
    model_revision: Reference | None
    artifact_sha256: Digest
    runtime_sha256: Digest
    prompt_name: Reference | None = None
    prompt_version: Reference | None = None
    prompt_sha256: Digest | None = None
    taxonomy_version: Reference | None = None
    threshold_version: Reference | None = None
    preprocess_version: Reference | None = None
    postprocess_version: Reference | None = None
    dataset_version: Reference | None = None


class AlignmentReport(Contract):
    schema_version: Literal["alignment_report/1.0.0"] = "alignment_report/1.0.0"
    source_scope: Literal["SYNTHETIC_FIXTURE", "REAL_MODEL_DIAGNOSTIC"]
    input_sha256: Digest
    profile: AlignmentProfile
    profile_sha256: Digest
    sources: tuple[SourceReference, ...]
    expected_image_count: int
    observed_image_count: int
    missing_evidence_ids: tuple[Reference, ...]
    claims: tuple[ClaimAlignment, ...]
    advisory_only: Literal[True] = True
    human_review_required: Literal[True] = True
    policy_eligible: Literal[False] = False
    model_quality_qualified: Literal[False] = False


def canonical_digest(value: BaseModel) -> str:
    payload = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


_VISUAL_TYPES = frozenset(
    {
        ExtractionIssueType.DENT,
        ExtractionIssueType.CRACK,
        ExtractionIssueType.BREAKAGE,
        ExtractionIssueType.PACKAGING_DAMAGE,
    }
)

_REQUESTS: dict[Reason, EvidenceRequest] = {
    Reason.NON_VISUAL_CLAIM: EvidenceRequest.PROVIDE_NON_VISUAL_EVIDENCE,
    Reason.REFERENCE_OR_SEMANTIC_EVIDENCE_REQUIRED: EvidenceRequest.PROVIDE_REFERENCE_OR_DETAILS,
    Reason.NO_IMAGE_EVIDENCE: EvidenceRequest.PROVIDE_IMAGE,
    Reason.VISION_RESULT_MISSING: EvidenceRequest.COMPLETE_VISION_ANALYSIS,
    Reason.SOURCE_IDENTITY_INCOMPLETE: EvidenceRequest.VERIFY_SOURCE_IDENTITY,
    Reason.IMAGE_QUALITY_NOT_EVALUATED: EvidenceRequest.CHECK_IMAGE_QUALITY,
    Reason.IMAGE_NOT_USABLE: EvidenceRequest.RETAKE_CLEAR_PRODUCT_IMAGE,
}


def align_evidence(value: AlignmentInput) -> AlignmentReport:
    """Replay validated canonical results; never invoke a model or change business state."""
    # Revalidate even instances built through Pydantic's unchecked model_copy/model_construct.
    value = AlignmentInput.model_validate_json(value.model_dump_json())
    sources = {s.record.evidence_id: s for s in value.vision}
    claims: list[ClaimAlignment] = []
    for index, claim in enumerate(value.text.record.result.claims):
        reasons: set[Reason] = set()
        candidates: list[CandidateLink] = []
        if claim.location is not DefectLocation.UNKNOWN:
            reasons.add(Reason.CLAIM_LOCATION_UNVERIFIED)
        if claim.type is ExtractionIssueType.FUNCTIONAL_FAILURE:
            reasons.add(Reason.NON_VISUAL_CLAIM)
        elif claim.type not in _VISUAL_TYPES:
            reasons.add(Reason.REFERENCE_OR_SEMANTIC_EVIDENCE_REQUIRED)
        elif value.text.metadata.model_revision is None:
            reasons.add(Reason.SOURCE_IDENTITY_INCOMPLETE)
        elif not value.snapshots:
            reasons.add(Reason.NO_IMAGE_EVIDENCE)
        else:
            for snapshot in sorted(value.snapshots, key=lambda s: s.position):
                source = sources.get(snapshot.evidence_id)
                if source is None:
                    reasons.add(Reason.VISION_RESULT_MISSING)
                    continue
                result = source.record.result
                if result.image_assessment is not None:
                    reasons.add(Reason.IMAGE_LEVEL_ONLY)
                if result.model_revision is None:
                    reasons.add(Reason.SOURCE_IDENTITY_INCOMPLETE)
                    continue
                quality = result.image_quality
                if quality.usable is ImageUsability.NOT_EVALUATED:
                    reasons.add(Reason.IMAGE_QUALITY_NOT_EVALUATED)
                    continue
                if (
                    quality.usable is not ImageUsability.USABLE
                    or quality.rejection_reasons
                    or quality.blurred is True
                    or quality.dark is True
                    or quality.overexposed is True
                    or quality.product_visible is False
                    or quality.defect_area_visible is False
                ):
                    reasons.add(Reason.IMAGE_NOT_USABLE)
                    continue
                if result.image_assessment is not None:
                    reasons.add(Reason.IMAGE_LEVEL_ONLY)
                    continue
                matching = [d for d in result.detections if d.label.value == claim.type.value]
                if not matching:
                    reasons.add(
                        Reason.DIFFERENT_TYPE_NOT_COUNTEREVIDENCE
                        if result.detections
                        else Reason.NO_TYPED_DETECTION
                    )
                for detection in sorted(matching, key=lambda d: d.id):
                    if detection.confidence < value.profile.detection_min_score:
                        reasons.add(Reason.BELOW_PROFILE_THRESHOLD)
                        continue
                    candidates.append(
                        CandidateLink(
                            evidence_id=snapshot.evidence_id,
                            vision_result_id=source.record.id,
                            detection_id=detection.id,
                            evidence_sha256=snapshot.sha256,
                        )
                    )
            if candidates:
                reasons.add(Reason.TYPE_MATCH_ONLY)
        requests = {_REQUESTS[r] for r in reasons if r in _REQUESTS}
        # A type match cannot verify the claim's location, severity or causal description.
        if claim.type in _VISUAL_TYPES:
            requests.add(EvidenceRequest.REVIEW_CLAIMED_AREA)
        claims.append(
            ClaimAlignment(
                claim_index=index,
                claim_type=claim.type,
                claimed_location=claim.location,
                status=AlignmentStatus.TYPE_CANDIDATE if candidates else AlignmentStatus.UNRESOLVED,
                candidates=tuple(candidates),
                reasons=tuple(sorted(reasons)),
                evidence_requests=tuple(sorted(requests)),
            )
        )
    text = value.text
    metadata = text.metadata
    refs = [
        SourceReference(
            result_id=text.record.id,
            stage_run_id=text.record.stage_run_id,
            result_sha256=canonical_digest(text.record),
            result_schema_version=text.record.result.schema_version,
            provider=metadata.provider_name,
            model=metadata.model_name,
            model_version=metadata.model_version,
            model_revision=metadata.model_revision,
            artifact_sha256=text.artifact_sha256,
            runtime_sha256=text.runtime_sha256,
            prompt_name=text.prompt_name,
            prompt_version=text.prompt_version,
            prompt_sha256=text.prompt_sha256,
        )
    ]
    for snapshot in sorted(value.snapshots, key=lambda s: s.position):
        source = sources.get(snapshot.evidence_id)
        if source is None:
            continue
        result = source.record.result
        refs.append(
            SourceReference(
                result_id=source.record.id,
                stage_run_id=source.record.stage_run_id,
                evidence_id=snapshot.evidence_id,
                evidence_sha256=snapshot.sha256,
                result_sha256=canonical_digest(source.record),
                result_schema_version=result.schema_version,
                provider=result.provider_name,
                model=result.model_name,
                model_version=result.model_version,
                model_revision=result.model_revision,
                artifact_sha256=source.artifact_sha256,
                runtime_sha256=source.runtime_sha256,
                taxonomy_version=result.taxonomy_version,
                threshold_version=result.threshold_version,
                preprocess_version=result.preprocess_version,
                postprocess_version=result.postprocess_version,
                dataset_version=result.dataset_version,
            )
        )
    return AlignmentReport(
        source_scope=value.source_scope,
        input_sha256=canonical_digest(value),
        profile=value.profile,
        profile_sha256=canonical_digest(value.profile),
        sources=tuple(refs),
        expected_image_count=len(value.snapshots),
        observed_image_count=len(value.vision),
        missing_evidence_ids=tuple(
            s.evidence_id
            for s in sorted(value.snapshots, key=lambda s: s.position)
            if s.evidence_id not in sources
        ),
        claims=tuple(claims),
    )
