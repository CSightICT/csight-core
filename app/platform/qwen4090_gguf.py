"""Additive GGUF/llama.cpp candidate contracts for the RTX 4090 release gate."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.model_activation import ModelArtifactFormat, ModelRuntimeEngine
from app.platform.qwen4090_release import (
    CalibrationEvidenceMode,
    CandidateReleaseStatus,
    CandidateRole,
    CandidateSource,
    Qwen4090Candidate,
    Qwen4090QualificationEvidence,
    QwenArtifactIdentity,
    QwenServingProfile,
    RTX4090ReleaseThresholds,
    assess_candidate,
)

_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"
_REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
_FILENAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{1,254}\.gguf$"


class CandidateSourceV2(StrEnum):
    OFFICIAL_QWEN = "OFFICIAL_QWEN"
    COMMUNITY = "COMMUNITY"
    CSIGHT = "CSIGHT"


class GGUFQuantizationType(StrEnum):
    Q4_K_M = "Q4_K_M"
    Q5_K_S = "Q5_K_S"


class GGUFQuantizationVariant(StrEnum):
    UNKNOWN_LEGACY = "UNKNOWN_LEGACY"
    NO_IMATRIX_Q4_K_M = "NO_IMATRIX_Q4_K_M"
    IMATRIX_Q4_K_M = "IMATRIX_Q4_K_M"
    MIXED_Q4_Q6 = "MIXED_Q4_Q6"
    IMATRIX_Q5_K_S = "IMATRIX_Q5_K_S"


class CandidateReleaseStatusV2(StrEnum):
    HARDWARE_EXCLUDED = "HARDWARE_EXCLUDED"
    PENDING_QUALIFICATION = "PENDING_QUALIFICATION"
    SHADOW_CANDIDATE = "SHADOW_CANDIDATE"
    RELEASE_ELIGIBLE = "RELEASE_ELIGIBLE"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LegacyCandidateBaseline(_Contract):
    matrix_schema_version: Literal["qwen4090_candidate_matrix/1.0.0"]
    matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")


class QwenGGUFArtifactIdentity(_Contract):
    artifact_format: Literal[ModelArtifactFormat.GGUF] = ModelArtifactFormat.GGUF
    artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    artifact_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    artifact_content_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    source: Literal[CandidateSourceV2.CSIGHT] = CandidateSourceV2.CSIGHT
    upstream_model_artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    upstream_model_revision: str = Field(pattern=_REVISION_PATTERN)
    base_artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    base_revision: str = Field(pattern=_REVISION_PATTERN)
    base_artifact_content_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    gguf_filename: str = Field(pattern=_FILENAME_PATTERN)
    weight_bytes: int | None = Field(default=None, gt=0)
    quantization_type: GGUFQuantizationType
    quantization_variant: GGUFQuantizationVariant = GGUFQuantizationVariant.UNKNOWN_LEGACY
    quantization_recipe_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    calibration_dataset_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    calibration_manifest_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    importance_matrix_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    tokenizer_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    chat_template_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    quantizer_binary_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    license_identifier: str = Field(min_length=2, max_length=128)

    @model_validator(mode="after")
    def prevent_requantized_lineage(self) -> QwenGGUFArtifactIdentity:
        if self.base_artifact == self.artifact:
            raise ValueError("CSight GGUF must identify the official unquantized base artifact")
        return self


class LlamaCppServingProfile(_Contract):
    runtime_engine: Literal[ModelRuntimeEngine.LLAMA_CPP] = ModelRuntimeEngine.LLAMA_CPP
    runtime_image: str = Field(min_length=2, max_length=255)
    runtime_image_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    runtime_binary_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    runtime_build_manifest_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    sbom_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    served_model_name: str = Field(min_length=2, max_length=255)
    max_context_tokens: int = Field(ge=1, le=1_000_000)
    max_num_sequences: int = Field(ge=1, le=4)
    gpu_layers: Literal["all"] = "all"
    batch_size: int = Field(ge=32, le=4096)
    ubatch_size: int = Field(ge=32, le=4096)
    flash_attention: Literal[True] = True
    kv_cache_type_k: Literal["q8_0", "f16"] = "q8_0"
    kv_cache_type_v: Literal["q8_0", "f16"] = "q8_0"
    api_compatibility: Literal["OPENAI_V1"] = "OPENAI_V1"
    language_model_only: Literal[True] = True
    automatic_cross_model_fallback: Literal[False] = False

    @model_validator(mode="after")
    def require_valid_batches(self) -> LlamaCppServingProfile:
        if self.ubatch_size > self.batch_size:
            raise ValueError("llama.cpp ubatch size cannot exceed batch size")
        return self


class Qwen4090GGUFCandidate(_Contract):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    role: Literal[CandidateRole.MODEL_CHALLENGER] = CandidateRole.MODEL_CHALLENGER
    artifact: QwenGGUFArtifactIdentity
    serving: LlamaCppServingProfile
    qualification: Qwen4090QualificationEvidence | None = None


class Qwen4090CandidateMatrixV2(_Contract):
    schema_version: Literal["qwen4090_candidate_matrix/2.0.0"] = "qwen4090_candidate_matrix/2.0.0"
    recorded_at: datetime
    target_gpu_name: Literal["NVIDIA GeForce RTX 4090"] = "NVIDIA GeForce RTX 4090"
    qualification_dataset_version: str = Field(min_length=2, max_length=128)
    qualification_dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    thresholds: RTX4090ReleaseThresholds
    legacy_baseline: LegacyCandidateBaseline
    candidates: tuple[Qwen4090GGUFCandidate, ...] = Field(min_length=1)

    @field_validator("recorded_at")
    @classmethod
    def require_utc_recorded_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_unique_candidates_and_artifacts(self) -> Qwen4090CandidateMatrixV2:
        identities = tuple(item.candidate_id for item in self.candidates)
        filenames = tuple(item.artifact.gguf_filename for item in self.candidates)
        if len(identities) != len(set(identities)):
            raise ValueError("candidate ids must be unique")
        if len(filenames) != len(set(filenames)):
            raise ValueError("GGUF filenames must be unique")
        return self

    @property
    def matrix_digest(self) -> str:
        content = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()


class LocalUnpublishedGGUFDevIdentity(_Contract):
    """Content identity for isolated canary/Dev execution before publication.

    This contract is deliberately not part of the signed release-manifest or
    activation unions. A local candidate has no artifact revision and may not
    be promoted, frozen, routed by Core, or used for sealed-Test evidence.
    """

    schema_version: Literal["local_unpublished_gguf_dev_identity/1.0.0"] = (
        "local_unpublished_gguf_dev_identity/1.0.0"
    )
    publication_state: Literal["LOCAL_UNPUBLISHED"] = "LOCAL_UNPUBLISHED"
    execution_scope: Literal["CANARY_DEV_ONLY"] = "CANARY_DEV_ONLY"
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    candidate_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    quantization_run_evidence_digest: str = Field(pattern=_DIGEST_PATTERN)

    artifact_source: Literal["CSIGHT"] = "CSIGHT"
    artifact_format: Literal[ModelArtifactFormat.GGUF] = ModelArtifactFormat.GGUF
    artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    artifact_revision: None = None
    artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    artifact_weight_bytes: int = Field(gt=0)
    upstream_model_artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    upstream_model_revision: str = Field(pattern=_REVISION_PATTERN)
    base_artifact: str = Field(pattern=_REPOSITORY_PATTERN)
    base_revision: str = Field(pattern=_REVISION_PATTERN)
    base_artifact_content_digest: str = Field(pattern=_DIGEST_PATTERN)
    gguf_filename: str = Field(pattern=_FILENAME_PATTERN)
    quantization_type: GGUFQuantizationType
    quantization_variant: GGUFQuantizationVariant
    quantization_recipe_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_dataset_digest: str = Field(pattern=_DIGEST_PATTERN)
    calibration_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    importance_matrix_digest: str = Field(pattern=_DIGEST_PATTERN)
    tokenizer_digest: str = Field(pattern=_DIGEST_PATTERN)
    chat_template_digest: str = Field(pattern=_DIGEST_PATTERN)
    quantizer_binary_digest: str = Field(pattern=_DIGEST_PATTERN)

    runtime_engine: Literal[ModelRuntimeEngine.LLAMA_CPP] = ModelRuntimeEngine.LLAMA_CPP
    runtime_image: str = Field(min_length=2, max_length=255)
    runtime_image_digest: str = Field(pattern=_DIGEST_PATTERN)
    llama_cpp_revision: str = Field(pattern=_REVISION_PATTERN)
    runtime_binary_digest: str = Field(pattern=_DIGEST_PATTERN)
    runtime_build_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    sbom_digest: str = Field(pattern=_DIGEST_PATTERN)
    served_model_name: str = Field(min_length=2, max_length=255)
    device_profile: Literal["onprem-cuda"] = "onprem-cuda"
    max_context_tokens: int = Field(ge=1, le=1_000_000)
    max_num_sequences: Literal[1] = 1
    gpu_layers: Literal["all"] = "all"
    batch_size: int = Field(ge=32, le=4096)
    ubatch_size: int = Field(ge=32, le=4096)
    flash_attention: Literal[True] = True
    kv_cache_type_k: Literal["q8_0"] = "q8_0"
    kv_cache_type_v: Literal["q8_0"] = "q8_0"
    api_compatibility: Literal["OPENAI_V1"] = "OPENAI_V1"
    language_model_only: Literal[True] = True
    automatic_cross_model_fallback: Literal[False] = False

    release_eligible: Literal[False] = False
    primary_allowed: Literal[False] = False
    core_routing_allowed: Literal[False] = False
    sealed_test_allowed: Literal[False] = False
    freeze_allowed: Literal[False] = False
    raw_customer_data_allowed: Literal[False] = False

    @model_validator(mode="after")
    def require_valid_local_dev_profile(self) -> LocalUnpublishedGGUFDevIdentity:
        if self.ubatch_size > self.batch_size:
            raise ValueError("llama.cpp ubatch size cannot exceed batch size")
        if self.quantization_variant is GGUFQuantizationVariant.UNKNOWN_LEGACY:
            raise ValueError("local unpublished Dev requires an explicit quantization variant")
        return self

    @property
    def identity_digest(self) -> str:
        content = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()

    @classmethod
    def from_candidate(
        cls,
        candidate: Qwen4090GGUFCandidate,
        *,
        candidate_matrix_digest: str,
        quantization_run_evidence_digest: str,
    ) -> LocalUnpublishedGGUFDevIdentity:
        artifact = candidate.artifact
        serving = candidate.serving
        if artifact.artifact_revision is not None:
            raise ValueError("local unpublished Dev identity requires artifact_revision=null")
        if candidate.qualification is not None:
            raise ValueError("qualified candidates cannot use the local unpublished Dev identity")
        required = {
            "artifact_content_digest": artifact.artifact_content_digest,
            "artifact_weight_bytes": artifact.weight_bytes,
            "base_artifact_content_digest": artifact.base_artifact_content_digest,
            "quantization_recipe_digest": artifact.quantization_recipe_digest,
            "calibration_dataset_digest": artifact.calibration_dataset_digest,
            "calibration_manifest_digest": artifact.calibration_manifest_digest,
            "importance_matrix_digest": artifact.importance_matrix_digest,
            "tokenizer_digest": artifact.tokenizer_digest,
            "chat_template_digest": artifact.chat_template_digest,
            "quantizer_binary_digest": artifact.quantizer_binary_digest,
            "runtime_image_digest": serving.runtime_image_digest,
            "llama_cpp_revision": serving.llama_cpp_revision,
            "runtime_binary_digest": serving.runtime_binary_digest,
            "runtime_build_manifest_digest": serving.runtime_build_manifest_digest,
            "sbom_digest": serving.sbom_digest,
        }
        missing = tuple(name for name, value in required.items() if value is None)
        if missing:
            raise ValueError(
                "local unpublished Dev identity is missing pinned content: " + ", ".join(missing)
            )
        if (
            serving.max_num_sequences != 1
            or serving.kv_cache_type_k != "q8_0"
            or serving.kv_cache_type_v != "q8_0"
        ):
            raise ValueError("local unpublished Dev requires concurrency 1 and Q8_0 K/V cache")
        assert artifact.artifact_content_digest is not None
        assert artifact.weight_bytes is not None
        assert artifact.base_artifact_content_digest is not None
        assert artifact.quantization_recipe_digest is not None
        assert artifact.calibration_dataset_digest is not None
        assert artifact.calibration_manifest_digest is not None
        assert artifact.importance_matrix_digest is not None
        assert artifact.tokenizer_digest is not None
        assert artifact.chat_template_digest is not None
        assert artifact.quantizer_binary_digest is not None
        assert serving.runtime_image_digest is not None
        assert serving.llama_cpp_revision is not None
        assert serving.runtime_binary_digest is not None
        assert serving.runtime_build_manifest_digest is not None
        assert serving.sbom_digest is not None
        return cls(
            candidate_id=candidate.candidate_id,
            candidate_matrix_digest=candidate_matrix_digest,
            quantization_run_evidence_digest=quantization_run_evidence_digest,
            artifact=artifact.artifact,
            artifact_content_digest=artifact.artifact_content_digest,
            artifact_weight_bytes=artifact.weight_bytes,
            upstream_model_artifact=artifact.upstream_model_artifact,
            upstream_model_revision=artifact.upstream_model_revision,
            base_artifact=artifact.base_artifact,
            base_revision=artifact.base_revision,
            base_artifact_content_digest=artifact.base_artifact_content_digest,
            gguf_filename=artifact.gguf_filename,
            quantization_type=artifact.quantization_type,
            quantization_variant=artifact.quantization_variant,
            quantization_recipe_digest=artifact.quantization_recipe_digest,
            calibration_dataset_digest=artifact.calibration_dataset_digest,
            calibration_manifest_digest=artifact.calibration_manifest_digest,
            importance_matrix_digest=artifact.importance_matrix_digest,
            tokenizer_digest=artifact.tokenizer_digest,
            chat_template_digest=artifact.chat_template_digest,
            quantizer_binary_digest=artifact.quantizer_binary_digest,
            runtime_image=serving.runtime_image,
            runtime_image_digest=serving.runtime_image_digest,
            llama_cpp_revision=serving.llama_cpp_revision,
            runtime_binary_digest=serving.runtime_binary_digest,
            runtime_build_manifest_digest=serving.runtime_build_manifest_digest,
            sbom_digest=serving.sbom_digest,
            served_model_name=serving.served_model_name,
            max_context_tokens=serving.max_context_tokens,
            max_num_sequences=1,
            gpu_layers=serving.gpu_layers,
            batch_size=serving.batch_size,
            ubatch_size=serving.ubatch_size,
            flash_attention=serving.flash_attention,
            kv_cache_type_k="q8_0",
            kv_cache_type_v="q8_0",
            api_compatibility=serving.api_compatibility,
            language_model_only=serving.language_model_only,
            automatic_cross_model_fallback=serving.automatic_cross_model_fallback,
        )


class CandidateAssessmentV2(_Contract):
    candidate_id: str
    status: CandidateReleaseStatusV2
    reason_codes: tuple[str, ...]


def _missing_package_fields(candidate: Qwen4090GGUFCandidate) -> tuple[str, ...]:
    fields = {
        "ARTIFACT_REVISION_UNPINNED": candidate.artifact.artifact_revision,
        "ARTIFACT_CONTENT_DIGEST_UNPINNED": candidate.artifact.artifact_content_digest,
        "BASE_ARTIFACT_CONTENT_DIGEST_UNPINNED": (candidate.artifact.base_artifact_content_digest),
        "ARTIFACT_WEIGHT_BYTES_UNPINNED": candidate.artifact.weight_bytes,
        "QUANTIZATION_RECIPE_UNPINNED": candidate.artifact.quantization_recipe_digest,
        "CALIBRATION_DATASET_UNPINNED": candidate.artifact.calibration_dataset_digest,
        "CALIBRATION_MANIFEST_UNPINNED": candidate.artifact.calibration_manifest_digest,
        "IMPORTANCE_MATRIX_UNPINNED": candidate.artifact.importance_matrix_digest,
        "TOKENIZER_DIGEST_UNPINNED": candidate.artifact.tokenizer_digest,
        "CHAT_TEMPLATE_DIGEST_UNPINNED": candidate.artifact.chat_template_digest,
        "QUANTIZER_BINARY_DIGEST_UNPINNED": candidate.artifact.quantizer_binary_digest,
        "RUNTIME_IMAGE_DIGEST_UNPINNED": candidate.serving.runtime_image_digest,
        "LLAMA_CPP_REVISION_UNPINNED": candidate.serving.llama_cpp_revision,
        "RUNTIME_BINARY_DIGEST_UNPINNED": candidate.serving.runtime_binary_digest,
        "RUNTIME_BUILD_MANIFEST_UNPINNED": candidate.serving.runtime_build_manifest_digest,
        "SBOM_UNPINNED": candidate.serving.sbom_digest,
    }
    return tuple(name for name, value in fields.items() if value is None)


def _legacy_assessment_proxy(
    candidate: Qwen4090GGUFCandidate,
    matrix: Qwen4090CandidateMatrixV2,
):
    artifact = candidate.artifact
    serving = candidate.serving
    assert artifact.artifact_revision is not None
    assert artifact.artifact_content_digest is not None
    assert artifact.weight_bytes is not None
    assert artifact.quantization_recipe_digest is not None
    assert artifact.calibration_dataset_digest is not None
    assert serving.runtime_image_digest is not None
    assert serving.runtime_build_manifest_digest is not None
    assert serving.sbom_digest is not None
    proxy = Qwen4090Candidate(
        candidate_id=candidate.candidate_id,
        role=CandidateRole.MODEL_CHALLENGER,
        artifact=QwenArtifactIdentity(
            artifact=artifact.artifact,
            artifact_revision=artifact.artifact_revision,
            artifact_content_digest=artifact.artifact_content_digest,
            source=CandidateSource.COMMUNITY,
            base_artifact=artifact.upstream_model_artifact,
            base_revision=artifact.upstream_model_revision,
            weight_bytes=artifact.weight_bytes,
            quantization_format=f"GGUF_{artifact.quantization_type.value}",
            quantization_recipe_digest=artifact.quantization_recipe_digest,
            calibration_evidence_mode=CalibrationEvidenceMode.DATASET_DIGEST_REQUIRED,
            calibration_dataset_digest=artifact.calibration_dataset_digest,
            license_identifier=artifact.license_identifier,
        ),
        serving=QwenServingProfile(
            runtime_image=serving.runtime_image,
            runtime_image_digest=serving.runtime_image_digest,
            dependency_lock_digest=serving.runtime_build_manifest_digest,
            sbom_digest=serving.sbom_digest,
            served_model_name=serving.served_model_name,
            max_context_tokens=serving.max_context_tokens,
            max_num_sequences=serving.max_num_sequences,
            gpu_memory_utilization=1.0,
            kv_cache_dtype=serving.kv_cache_type_k,
            language_model_only=serving.language_model_only,
            automatic_cross_model_fallback=serving.automatic_cross_model_fallback,
        ),
        qualification=candidate.qualification,
    )
    return assess_candidate(
        proxy,
        target_gpu_name=matrix.target_gpu_name,
        qualification_dataset_version=matrix.qualification_dataset_version,
        qualification_dataset_digest=matrix.qualification_dataset_digest,
        thresholds=matrix.thresholds,
    )


def assess_gguf_candidate(
    candidate: Qwen4090GGUFCandidate,
    *,
    matrix: Qwen4090CandidateMatrixV2,
) -> CandidateAssessmentV2:
    organization_owned = candidate.artifact.artifact.split("/", 1)[0] == "CSightICT"
    weight_bytes = candidate.artifact.weight_bytes
    if weight_bytes is not None and weight_bytes > matrix.thresholds.total_vram_mib * 1024 * 1024:
        return CandidateAssessmentV2(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatusV2.HARDWARE_EXCLUDED,
            reason_codes=("WEIGHTS_EXCEED_DEVICE_VRAM",),
        )
    missing = _missing_package_fields(candidate)
    if missing:
        return CandidateAssessmentV2(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatusV2.PENDING_QUALIFICATION,
            reason_codes=(
                missing if organization_owned else (*missing, "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED")
            ),
        )
    if candidate.qualification is None:
        return CandidateAssessmentV2(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatusV2.SHADOW_CANDIDATE,
            reason_codes=(
                ("RELEASE_QUALIFICATION_NOT_RUN",)
                if organization_owned
                else (
                    "RELEASE_QUALIFICATION_NOT_RUN",
                    "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED",
                )
            ),
        )
    legacy = _legacy_assessment_proxy(candidate, matrix)
    if not organization_owned:
        return CandidateAssessmentV2(
            candidate_id=candidate.candidate_id,
            status=CandidateReleaseStatusV2.SHADOW_CANDIDATE,
            reason_codes=(*legacy.reason_codes, "ORG_OWNED_ARTIFACT_MIRROR_REQUIRED"),
        )
    return CandidateAssessmentV2(
        candidate_id=candidate.candidate_id,
        status=(
            CandidateReleaseStatusV2.RELEASE_ELIGIBLE
            if legacy.status is CandidateReleaseStatus.RELEASE_ELIGIBLE
            else CandidateReleaseStatusV2.SHADOW_CANDIDATE
        ),
        reason_codes=legacy.reason_codes,
    )


def assess_gguf_matrix(
    matrix: Qwen4090CandidateMatrixV2,
) -> tuple[CandidateAssessmentV2, ...]:
    return tuple(assess_gguf_candidate(candidate, matrix=matrix) for candidate in matrix.candidates)


__all__ = [
    "CandidateAssessmentV2",
    "CandidateReleaseStatusV2",
    "CandidateSourceV2",
    "GGUFQuantizationType",
    "GGUFQuantizationVariant",
    "LegacyCandidateBaseline",
    "LlamaCppServingProfile",
    "LocalUnpublishedGGUFDevIdentity",
    "Qwen4090CandidateMatrixV2",
    "Qwen4090GGUFCandidate",
    "QwenGGUFArtifactIdentity",
    "assess_gguf_candidate",
    "assess_gguf_matrix",
]
