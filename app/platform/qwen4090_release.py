"""Technology-neutral RTX 4090 Qwen candidate qualification gates."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"


class CandidateSource(StrEnum):
    OFFICIAL_QWEN = "OFFICIAL_QWEN"
    COMMUNITY = "COMMUNITY"


class CandidateRole(StrEnum):
    BASELINE = "BASELINE"
    MODEL_CHALLENGER = "MODEL_CHALLENGER"
    RUNTIME_CHALLENGER = "RUNTIME_CHALLENGER"
    HARDWARE_PREFLIGHT = "HARDWARE_PREFLIGHT"


class CalibrationEvidenceMode(StrEnum):
    DATASET_DIGEST_REQUIRED = "DATASET_DIGEST_REQUIRED"
    OFFICIAL_PREQUANTIZED_DYNAMIC_FP8 = "OFFICIAL_PREQUANTIZED_DYNAMIC_FP8"


class CandidateReleaseStatus(StrEnum):
    HARDWARE_EXCLUDED = "HARDWARE_EXCLUDED"
    PENDING_QUALIFICATION = "PENDING_QUALIFICATION"
    SHADOW_ONLY = "SHADOW_ONLY"
    RELEASE_ELIGIBLE = "RELEASE_ELIGIBLE"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RTX4090ReleaseThresholds(_Contract):
    total_vram_mib: int = Field(ge=20_000, le=30_000)
    minimum_observed_free_vram_mib: int = Field(ge=1)
    minimum_shadow_cases: int = Field(ge=100)
    minimum_workflow_cases: int = Field(ge=20)
    minimum_issue_f1: float = Field(ge=0.0, le=1.0)
    minimum_requested_action_set_f1: float = Field(ge=0.0, le=1.0)
    minimum_requested_action_exact_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_system_missing_exact_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_action_consistency_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_text_ambiguity_set_f1: float = Field(ge=0.0, le=1.0)
    maximum_latency_p95_seconds: float = Field(gt=0.0)
    minimum_output_tokens_per_second: float = Field(gt=0.0)
    minimum_soak_minutes: float = Field(ge=20.0)

    @model_validator(mode="after")
    def free_memory_must_fit_device(self) -> RTX4090ReleaseThresholds:
        if self.minimum_observed_free_vram_mib >= self.total_vram_mib:
            raise ValueError("minimum free VRAM must be smaller than device VRAM")
        return self


class QwenArtifactIdentity(_Contract):
    artifact: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    artifact_revision: str = Field(pattern=_REVISION_PATTERN)
    artifact_content_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    source: CandidateSource
    base_artifact: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    base_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    weight_bytes: int = Field(gt=0)
    quantization_format: str = Field(min_length=2, max_length=128)
    quantization_recipe_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    calibration_evidence_mode: CalibrationEvidenceMode = (
        CalibrationEvidenceMode.DATASET_DIGEST_REQUIRED
    )
    calibration_dataset_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    license_identifier: str = Field(min_length=2, max_length=128)

    @model_validator(mode="after")
    def validate_calibration_evidence_mode(self) -> QwenArtifactIdentity:
        if (
            self.calibration_evidence_mode
            is CalibrationEvidenceMode.OFFICIAL_PREQUANTIZED_DYNAMIC_FP8
        ):
            if (
                self.source is not CandidateSource.OFFICIAL_QWEN
                or "FP8" not in self.quantization_format
            ):
                raise ValueError(
                    "dynamic FP8 calibration exemption requires an official FP8 artifact"
                )
            if self.calibration_dataset_digest is not None:
                raise ValueError("dynamic FP8 calibration exemption cannot carry a dataset digest")
        return self


class QwenServingProfile(_Contract):
    runtime_image: str = Field(min_length=2, max_length=255)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    dependency_lock_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    sbom_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    served_model_name: str = Field(min_length=2, max_length=255)
    max_context_tokens: int = Field(ge=1, le=1_000_000)
    max_num_sequences: int = Field(ge=1, le=64)
    gpu_memory_utilization: float = Field(gt=0.0, le=1.0)
    kv_cache_dtype: str = Field(min_length=2, max_length=64)
    language_model_only: bool
    automatic_cross_model_fallback: bool


class Qwen4090QualificationEvidence(_Contract):
    measured_gpu_name: str = Field(min_length=2, max_length=128)
    measured_gpu_count: int = Field(ge=1, le=8)
    measured_total_vram_mib: int = Field(gt=0)
    dataset_version: str = Field(min_length=2, max_length=128)
    dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    result_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    evaluation_contract_unambiguous: bool
    shadow_cases: int = Field(ge=0)
    workflow_cases: int = Field(ge=0)
    terminal_workflow_cases: int = Field(ge=0)
    json_schema_valid_rate: float = Field(ge=0.0, le=1.0)
    pydantic_valid_rate: float = Field(ge=0.0, le=1.0)
    exact_quote_rate: float = Field(ge=0.0, le=1.0)
    issue_f1: float = Field(ge=0.0, le=1.0)
    requested_action_set_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    requested_action_exact_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    system_missing_exact_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    action_consistency_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    text_ambiguity_set_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    legacy_v1_requested_action_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    legacy_v1_missing_information_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    forbidden_field_rate: float = Field(ge=0.0, le=1.0)
    injection_violation_rate: float = Field(ge=0.0, le=1.0)
    reasoning_leakage_rate: float = Field(ge=0.0, le=1.0)
    observed_min_free_vram_mib: int = Field(ge=0)
    latency_p95_seconds: float = Field(gt=0.0)
    output_tokens_per_second: float = Field(gt=0.0)
    soak_minutes: float = Field(ge=0.0)
    oom_count: int = Field(ge=0)
    restart_count: int = Field(ge=0)
    stalled_workflow_count: int = Field(ge=0)
    duplicate_terminal_count: int = Field(ge=0)
    metadata_complete_rate: float = Field(ge=0.0, le=1.0)
    measured_at: datetime | None = None

    @field_validator("measured_at")
    @classmethod
    def require_utc_measurement(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_workflow_counts(self) -> Qwen4090QualificationEvidence:
        if self.terminal_workflow_cases > self.workflow_cases:
            raise ValueError("terminal workflow count cannot exceed workflow count")
        if self.observed_min_free_vram_mib > self.measured_total_vram_mib:
            raise ValueError("observed free VRAM cannot exceed measured device VRAM")
        return self


class Qwen4090Candidate(_Contract):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    role: CandidateRole
    artifact: QwenArtifactIdentity
    serving: QwenServingProfile
    qualification: Qwen4090QualificationEvidence | None = None


class Qwen4090CandidateMatrix(_Contract):
    schema_version: str = Field(pattern=r"^qwen4090_candidate_matrix/1\.0\.0$")
    recorded_at: datetime
    target_gpu_name: str = Field(pattern=r"^NVIDIA GeForce RTX 4090$")
    qualification_dataset_version: str = Field(min_length=2, max_length=128)
    qualification_dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    thresholds: RTX4090ReleaseThresholds
    candidates: tuple[Qwen4090Candidate, ...] = Field(min_length=1)

    @field_validator("recorded_at")
    @classmethod
    def require_utc_recorded_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_unique_candidates_and_one_baseline(self) -> Qwen4090CandidateMatrix:
        identities = tuple(item.candidate_id for item in self.candidates)
        if len(identities) != len(set(identities)):
            raise ValueError("candidate ids must be unique")
        if sum(item.role is CandidateRole.BASELINE for item in self.candidates) != 1:
            raise ValueError("candidate matrix must contain exactly one baseline")
        return self


class CandidateAssessment(_Contract):
    candidate_id: str
    status: CandidateReleaseStatus
    reason_codes: tuple[str, ...]


def assess_candidate(
    candidate: Qwen4090Candidate,
    *,
    target_gpu_name: str,
    qualification_dataset_version: str,
    qualification_dataset_digest: str,
    thresholds: RTX4090ReleaseThresholds,
) -> CandidateAssessment:
    """Return a fail-closed hardware-specific release decision."""

    device_bytes = thresholds.total_vram_mib * 1024 * 1024
    if candidate.artifact.weight_bytes > device_bytes:
        return CandidateAssessment(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatus.HARDWARE_EXCLUDED,
            reason_codes=("WEIGHTS_EXCEED_DEVICE_VRAM",),
        )

    evidence = candidate.qualification
    if evidence is None:
        return CandidateAssessment(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatus.PENDING_QUALIFICATION,
            reason_codes=("QUALIFICATION_NOT_RUN",),
        )

    failures: list[str] = []
    required_package_fields = {
        "ARTIFACT_CONTENT_DIGEST_UNPINNED": candidate.artifact.artifact_content_digest,
        "QUANTIZATION_RECIPE_UNPINNED": candidate.artifact.quantization_recipe_digest,
        "DEPENDENCY_LOCK_UNPINNED": candidate.serving.dependency_lock_digest,
        "SBOM_UNPINNED": candidate.serving.sbom_digest,
        "QUALIFICATION_RESULT_DIGEST_UNPINNED": evidence.result_digest,
        "MEASURED_AT_UNPINNED": evidence.measured_at,
    }
    if (
        candidate.artifact.calibration_evidence_mode
        is CalibrationEvidenceMode.DATASET_DIGEST_REQUIRED
    ):
        required_package_fields["CALIBRATION_DATASET_UNPINNED"] = (
            candidate.artifact.calibration_dataset_digest
        )
    failures.extend(name for name, value in required_package_fields.items() if value is None)
    if evidence.measured_gpu_name != target_gpu_name or evidence.measured_gpu_count != 1:
        failures.append("WRONG_HARDWARE_PROFILE")
    if evidence.measured_total_vram_mib != thresholds.total_vram_mib:
        failures.append("VRAM_PROFILE_MISMATCH")
    if evidence.dataset_version != qualification_dataset_version:
        failures.append("QUALIFICATION_DATASET_VERSION_MISMATCH")
    if evidence.dataset_digest != qualification_dataset_digest:
        failures.append("QUALIFICATION_DATASET_DIGEST_MISMATCH")
    if candidate.serving.automatic_cross_model_fallback:
        failures.append("AUTOMATIC_CROSS_MODEL_FALLBACK_ENABLED")
    if not candidate.serving.language_model_only:
        failures.append("TEXT_ONLY_BOUNDARY_DISABLED")
    if not evidence.evaluation_contract_unambiguous:
        failures.append("EVALUATION_CONTRACT_AMBIGUOUS")
    if evidence.shadow_cases < thresholds.minimum_shadow_cases:
        failures.append("SHADOW_CASE_COUNT_BELOW_MINIMUM")
    if (
        evidence.workflow_cases < thresholds.minimum_workflow_cases
        or evidence.terminal_workflow_cases != evidence.workflow_cases
    ):
        failures.append("WORKFLOW_TERMINAL_GATE_FAILED")
    if evidence.json_schema_valid_rate != 1.0:
        failures.append("JSON_SCHEMA_GATE_FAILED")
    if evidence.pydantic_valid_rate != 1.0:
        failures.append("PYDANTIC_GATE_FAILED")
    if evidence.exact_quote_rate != 1.0:
        failures.append("EXACT_QUOTE_GATE_FAILED")
    if evidence.issue_f1 < thresholds.minimum_issue_f1:
        failures.append("ISSUE_F1_BELOW_MINIMUM")
    v2_metrics = {
        "REQUESTED_ACTION_SET_F1_NOT_RECORDED": evidence.requested_action_set_f1,
        "REQUESTED_ACTION_EXACT_ACCURACY_NOT_RECORDED": (evidence.requested_action_exact_accuracy),
        "SYSTEM_MISSING_EXACT_ACCURACY_NOT_RECORDED": (evidence.system_missing_exact_accuracy),
        "ACTION_CONSISTENCY_ACCURACY_NOT_RECORDED": evidence.action_consistency_accuracy,
        "TEXT_AMBIGUITY_SET_F1_NOT_RECORDED": evidence.text_ambiguity_set_f1,
    }
    failures.extend(name for name, value in v2_metrics.items() if value is None)
    if (
        evidence.requested_action_set_f1 is not None
        and evidence.requested_action_set_f1 < thresholds.minimum_requested_action_set_f1
    ):
        failures.append("REQUESTED_ACTION_SET_F1_BELOW_MINIMUM")
    if (
        evidence.requested_action_exact_accuracy is not None
        and evidence.requested_action_exact_accuracy
        < thresholds.minimum_requested_action_exact_accuracy
    ):
        failures.append("REQUESTED_ACTION_EXACT_ACCURACY_BELOW_MINIMUM")
    if (
        evidence.system_missing_exact_accuracy is not None
        and evidence.system_missing_exact_accuracy
        < thresholds.minimum_system_missing_exact_accuracy
    ):
        failures.append("SYSTEM_MISSING_EXACT_ACCURACY_BELOW_MINIMUM")
    if (
        evidence.action_consistency_accuracy is not None
        and evidence.action_consistency_accuracy < thresholds.minimum_action_consistency_accuracy
    ):
        failures.append("ACTION_CONSISTENCY_ACCURACY_BELOW_MINIMUM")
    if (
        evidence.text_ambiguity_set_f1 is not None
        and evidence.text_ambiguity_set_f1 < thresholds.minimum_text_ambiguity_set_f1
    ):
        failures.append("TEXT_AMBIGUITY_SET_F1_BELOW_MINIMUM")
    if any(
        rate != 0.0
        for rate in (
            evidence.forbidden_field_rate,
            evidence.injection_violation_rate,
            evidence.reasoning_leakage_rate,
        )
    ):
        failures.append("SAFETY_RATE_GATE_FAILED")
    if evidence.observed_min_free_vram_mib < thresholds.minimum_observed_free_vram_mib:
        failures.append("VRAM_HEADROOM_BELOW_MINIMUM")
    if evidence.latency_p95_seconds > thresholds.maximum_latency_p95_seconds:
        failures.append("LATENCY_P95_ABOVE_MAXIMUM")
    if evidence.output_tokens_per_second < thresholds.minimum_output_tokens_per_second:
        failures.append("OUTPUT_RATE_BELOW_MINIMUM")
    if evidence.soak_minutes < thresholds.minimum_soak_minutes:
        failures.append("SOAK_DURATION_BELOW_MINIMUM")
    if any(
        count != 0
        for count in (
            evidence.oom_count,
            evidence.restart_count,
            evidence.stalled_workflow_count,
            evidence.duplicate_terminal_count,
        )
    ):
        failures.append("RELIABILITY_GATE_FAILED")
    if evidence.metadata_complete_rate != 1.0:
        failures.append("METADATA_COMPLETENESS_GATE_FAILED")

    return CandidateAssessment(
        candidate_id=candidate.candidate_id,
        status=(
            CandidateReleaseStatus.SHADOW_ONLY
            if failures
            else CandidateReleaseStatus.RELEASE_ELIGIBLE
        ),
        reason_codes=tuple(dict.fromkeys(failures)),
    )


def assess_matrix(matrix: Qwen4090CandidateMatrix) -> tuple[CandidateAssessment, ...]:
    return tuple(
        assess_candidate(
            candidate,
            target_gpu_name=matrix.target_gpu_name,
            qualification_dataset_version=matrix.qualification_dataset_version,
            qualification_dataset_digest=matrix.qualification_dataset_digest,
            thresholds=matrix.thresholds,
        )
        for candidate in matrix.candidates
    )


__all__ = [
    "CalibrationEvidenceMode",
    "CandidateAssessment",
    "CandidateReleaseStatus",
    "CandidateRole",
    "CandidateSource",
    "Qwen4090Candidate",
    "Qwen4090CandidateMatrix",
    "Qwen4090QualificationEvidence",
    "QwenArtifactIdentity",
    "QwenServingProfile",
    "RTX4090ReleaseThresholds",
    "assess_candidate",
    "assess_matrix",
]
