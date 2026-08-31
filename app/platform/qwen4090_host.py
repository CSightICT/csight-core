"""Technology-neutral evidence contract for an RTX 4090 model-serving host."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.qwen4090_release import (
    CalibrationEvidenceMode,
    CandidateRole,
    Qwen4090Candidate,
    Qwen4090CandidateMatrix,
)

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"


class HostPreflightStatus(StrEnum):
    PASS = "PASS"
    SHADOW_READY_PROVENANCE_INCOMPLETE = "SHADOW_READY_PROVENANCE_INCOMPLETE"
    EVIDENCE_COLLECTED_NOT_PINNED = "EVIDENCE_COLLECTED_NOT_PINNED"
    FAIL = "FAIL"


class HostCheckStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RTX4090GpuHostEvidence(_Contract):
    name: str = Field(min_length=2, max_length=128)
    driver_version: str = Field(min_length=2, max_length=64)
    compute_capability: str = Field(pattern=r"^\d+\.\d+$")
    total_vram_mib: int = Field(gt=0)
    free_vram_mib: int = Field(ge=0)
    uuid_sha256: str = Field(pattern=_DIGEST_PATTERN)


class Qwen4090HostEvidence(_Contract):
    schema_version: str = Field(pattern=r"^qwen4090_host_evidence/1\.0\.0$")
    collected_at: datetime
    os_name: str = Field(min_length=2, max_length=64)
    machine: str = Field(min_length=2, max_length=64)
    kernel_release: str = Field(min_length=1, max_length=128)
    gpus: tuple[RTX4090GpuHostEvidence, ...]
    active_compute_process_count: int = Field(ge=0)
    docker_server_os: str = Field(min_length=2, max_length=64)
    docker_server_arch: str = Field(min_length=2, max_length=64)
    docker_server_version: str = Field(min_length=1, max_length=64)
    nvidia_runtime_available: bool
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_env_private: bool
    api_key_valid: bool
    hf_hub_offline: bool
    transformers_offline: bool
    bind_address_is_tailscale: bool
    bind_address_is_local: bool
    bind_address_sha256: str = Field(pattern=_DIGEST_PATTERN)
    artifact: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    artifact_revision: str = Field(pattern=_REVISION_PATTERN)
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    artifact_file_count: int = Field(gt=0)
    weight_bytes: int = Field(gt=0)
    dependency_lock_digest: str = Field(pattern=_DIGEST_PATTERN)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    quantization_recipe_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    calibration_dataset_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @field_validator("collected_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value.astimezone(UTC)


class Qwen4090HostCheck(_Contract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    status: HostCheckStatus
    reason_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,95}$")
    observed: str = Field(min_length=1, max_length=512)
    expected: str = Field(min_length=1, max_length=512)


class Qwen4090HostPreflightReport(_Contract):
    schema_version: str = Field(pattern=r"^qwen4090_host_preflight/1\.0\.0$")
    candidate_id: str
    status: HostPreflightStatus
    strict_ready: bool
    evidence: Qwen4090HostEvidence
    checks: tuple[Qwen4090HostCheck, ...]


def _candidate(matrix: Qwen4090CandidateMatrix, candidate_id: str) -> Qwen4090Candidate:
    candidates = tuple(item for item in matrix.candidates if item.candidate_id == candidate_id)
    if len(candidates) != 1:
        raise ValueError("candidate is not present exactly once in the frozen matrix")
    candidate = candidates[0]
    if candidate.role not in {CandidateRole.MODEL_CHALLENGER, CandidateRole.RUNTIME_CHALLENGER}:
        raise ValueError("host preflight is limited to runnable Shadow candidates")
    return candidate


def assess_qwen4090_host(
    matrix: Qwen4090CandidateMatrix,
    *,
    candidate_id: str,
    evidence: Qwen4090HostEvidence,
) -> Qwen4090HostPreflightReport:
    """Compare privacy-safe live host evidence with one exact frozen candidate."""

    candidate = _candidate(matrix, candidate_id)
    checks: list[Qwen4090HostCheck] = []

    def required(
        name: str,
        condition: bool,
        *,
        observed: object,
        expected: object,
        reason_code: str,
    ) -> None:
        checks.append(
            Qwen4090HostCheck(
                name=name,
                status=HostCheckStatus.PASS if condition else HostCheckStatus.FAIL,
                reason_code=None if condition else reason_code,
                observed=str(observed),
                expected=str(expected),
            )
        )

    def pinned(
        name: str,
        observed: str | None,
        expected: str | None,
        *,
        missing_code: str,
        mismatch_code: str,
    ) -> None:
        if expected is None:
            checks.append(
                Qwen4090HostCheck(
                    name=name,
                    status=HostCheckStatus.WARNING,
                    reason_code=missing_code,
                    observed=observed or "NOT_COLLECTED",
                    expected="PINNED_IN_CANDIDATE_MATRIX",
                )
            )
            return
        required(
            name,
            observed == expected,
            observed=observed or "NOT_COLLECTED",
            expected=expected,
            reason_code=mismatch_code,
        )

    required(
        "host_platform",
        evidence.os_name == "Linux" and evidence.machine in {"x86_64", "amd64"},
        observed=f"{evidence.os_name}/{evidence.machine}",
        expected="Linux/x86_64",
        reason_code="HOST_PLATFORM_MISMATCH",
    )
    required(
        "gpu_count",
        len(evidence.gpus) == 1,
        observed=len(evidence.gpus),
        expected=1,
        reason_code="GPU_COUNT_MISMATCH",
    )
    if evidence.gpus:
        gpu = evidence.gpus[0]
        required(
            "gpu_name",
            gpu.name == matrix.target_gpu_name,
            observed=gpu.name,
            expected=matrix.target_gpu_name,
            reason_code="GPU_NAME_MISMATCH",
        )
        required(
            "gpu_compute_capability",
            gpu.compute_capability == "8.9",
            observed=gpu.compute_capability,
            expected="8.9",
            reason_code="GPU_COMPUTE_CAPABILITY_MISMATCH",
        )
        required(
            "gpu_total_vram",
            gpu.total_vram_mib == matrix.thresholds.total_vram_mib,
            observed=gpu.total_vram_mib,
            expected=matrix.thresholds.total_vram_mib,
            reason_code="GPU_VRAM_PROFILE_MISMATCH",
        )
        required(
            "gpu_free_vram",
            gpu.free_vram_mib >= matrix.thresholds.minimum_observed_free_vram_mib,
            observed=gpu.free_vram_mib,
            expected=f">={matrix.thresholds.minimum_observed_free_vram_mib}",
            reason_code="GPU_FREE_VRAM_BELOW_PREFLIGHT_MINIMUM",
        )
    required(
        "gpu_compute_idle",
        evidence.active_compute_process_count == 0,
        observed=evidence.active_compute_process_count,
        expected=0,
        reason_code="GPU_COMPUTE_PROCESS_ALREADY_ACTIVE",
    )
    required(
        "docker_platform",
        evidence.docker_server_os == "linux" and evidence.docker_server_arch in {"x86_64", "amd64"},
        observed=f"{evidence.docker_server_os}/{evidence.docker_server_arch}",
        expected="linux/amd64",
        reason_code="DOCKER_PLATFORM_MISMATCH",
    )
    required(
        "docker_nvidia_runtime",
        evidence.nvidia_runtime_available,
        observed=evidence.nvidia_runtime_available,
        expected=True,
        reason_code="DOCKER_NVIDIA_RUNTIME_MISSING",
    )
    required(
        "runtime_env_private",
        evidence.runtime_env_private and evidence.api_key_valid,
        observed=f"private={evidence.runtime_env_private},key_valid={evidence.api_key_valid}",
        expected="private=True,key_valid=True",
        reason_code="RUNTIME_ENV_OR_API_KEY_UNSAFE",
    )
    required(
        "artifact_network_offline",
        evidence.hf_hub_offline and evidence.transformers_offline,
        observed=(
            f"hf_hub_offline={evidence.hf_hub_offline},"
            f"transformers_offline={evidence.transformers_offline}"
        ),
        expected="hf_hub_offline=True,transformers_offline=True",
        reason_code="ARTIFACT_NETWORK_OFFLINE_DISABLED",
    )
    required(
        "private_bind",
        evidence.bind_address_is_tailscale and evidence.bind_address_is_local,
        observed=(
            f"tailscale={evidence.bind_address_is_tailscale},"
            f"local={evidence.bind_address_is_local},hash={evidence.bind_address_sha256}"
        ),
        expected="tailscale=True,local=True",
        reason_code="PRIVATE_BIND_ADDRESS_INVALID",
    )
    required(
        "runtime_image",
        evidence.runtime_image_digest == candidate.serving.runtime_image_digest,
        observed=evidence.runtime_image_digest,
        expected=candidate.serving.runtime_image_digest,
        reason_code="RUNTIME_IMAGE_DIGEST_MISMATCH",
    )
    required(
        "artifact_identity",
        evidence.artifact == candidate.artifact.artifact
        and evidence.artifact_revision == candidate.artifact.artifact_revision,
        observed=f"{evidence.artifact}@{evidence.artifact_revision}",
        expected=f"{candidate.artifact.artifact}@{candidate.artifact.artifact_revision}",
        reason_code="ARTIFACT_IDENTITY_MISMATCH",
    )
    required(
        "artifact_weight_bytes",
        evidence.weight_bytes == candidate.artifact.weight_bytes,
        observed=evidence.weight_bytes,
        expected=candidate.artifact.weight_bytes,
        reason_code="ARTIFACT_WEIGHT_BYTES_MISMATCH",
    )
    pinned(
        "artifact_content_digest",
        evidence.artifact_content_digest,
        candidate.artifact.artifact_content_digest,
        missing_code="ARTIFACT_CONTENT_DIGEST_NOT_PINNED",
        mismatch_code="ARTIFACT_CONTENT_DIGEST_MISMATCH",
    )
    pinned(
        "dependency_lock_digest",
        evidence.dependency_lock_digest,
        candidate.serving.dependency_lock_digest,
        missing_code="DEPENDENCY_LOCK_DIGEST_NOT_PINNED",
        mismatch_code="DEPENDENCY_LOCK_DIGEST_MISMATCH",
    )
    pinned(
        "sbom_digest",
        evidence.sbom_digest,
        candidate.serving.sbom_digest,
        missing_code="SBOM_DIGEST_NOT_PINNED",
        mismatch_code="SBOM_DIGEST_MISMATCH",
    )
    pinned(
        "quantization_recipe_digest",
        evidence.quantization_recipe_digest,
        candidate.artifact.quantization_recipe_digest,
        missing_code="QUANTIZATION_RECIPE_DIGEST_NOT_PINNED",
        mismatch_code="QUANTIZATION_RECIPE_DIGEST_MISMATCH",
    )
    if (
        candidate.artifact.calibration_evidence_mode
        is CalibrationEvidenceMode.OFFICIAL_PREQUANTIZED_DYNAMIC_FP8
    ):
        required(
            "calibration_evidence_mode",
            evidence.calibration_dataset_digest is None,
            observed=(
                "NO_DATASET_DIGEST"
                if evidence.calibration_dataset_digest is None
                else evidence.calibration_dataset_digest
            ),
            expected=CalibrationEvidenceMode.OFFICIAL_PREQUANTIZED_DYNAMIC_FP8,
            reason_code="UNEXPECTED_CALIBRATION_DATASET_DIGEST",
        )
    else:
        pinned(
            "calibration_dataset_digest",
            evidence.calibration_dataset_digest,
            candidate.artifact.calibration_dataset_digest,
            missing_code="CALIBRATION_DATASET_DIGEST_NOT_PINNED",
            mismatch_code="CALIBRATION_DATASET_DIGEST_MISMATCH",
        )

    has_failure = any(item.status is HostCheckStatus.FAIL for item in checks)
    has_warning = any(item.status is HostCheckStatus.WARNING for item in checks)
    warning_reason_codes = {
        item.reason_code
        for item in checks
        if item.status is HostCheckStatus.WARNING and item.reason_code is not None
    }
    shadow_provenance_only = bool(warning_reason_codes) and warning_reason_codes <= {
        "CALIBRATION_DATASET_DIGEST_NOT_PINNED"
    }
    status = (
        HostPreflightStatus.FAIL
        if has_failure
        else (
            HostPreflightStatus.SHADOW_READY_PROVENANCE_INCOMPLETE
            if shadow_provenance_only
            else (
                HostPreflightStatus.EVIDENCE_COLLECTED_NOT_PINNED
                if has_warning
                else HostPreflightStatus.PASS
            )
        )
    )
    return Qwen4090HostPreflightReport(
        schema_version="qwen4090_host_preflight/1.0.0",
        candidate_id=candidate_id,
        status=status,
        strict_ready=status is HostPreflightStatus.PASS,
        evidence=evidence,
        checks=tuple(checks),
    )


__all__ = [
    "HostCheckStatus",
    "HostPreflightStatus",
    "Qwen4090HostCheck",
    "Qwen4090HostEvidence",
    "Qwen4090HostPreflightReport",
    "RTX4090GpuHostEvidence",
    "assess_qwen4090_host",
]
