"""Signed release, immutable activation, and runtime identity contracts."""

import base64
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.adapters.security.model_release_signatures import (
    Ed25519ModelReleaseSignatureVerifier,
)
from app.application.model_activation import RequireActiveModelRelease
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import (
    ActiveLLMRelease,
    ActiveModelReleaseRequiredError,
    LLMReleaseManifest,
    ModelActivationEvent,
    ModelReleaseIdentityMismatchError,
    ModelReleaseTask,
    RegisteredLLMRelease,
    RuntimeLLMIdentity,
    SignedLLMReleaseManifest,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


def _manifest() -> LLMReleaseManifest:
    digest = "sha256:" + "a" * 64
    return LLMReleaseManifest(
        candidate_id="qwen38-27b-int4-vllm028",
        package_name="csight-qwen38-27b-int4",
        package_version="2026.08.30.1",
        task=ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
        artifact="Qwen/Qwen3.8-27B",
        artifact_revision="1" * 40,
        artifact_content_digest=digest,
        runtime_image="vllm/vllm-openai",
        runtime_image_digest=digest,
        dependency_lock_digest=digest,
        sbom_digest=digest,
        served_model_name="csight-qwen38-27b",
        model_version="Qwen3.8-27B-INT4",
        prompt_name="product_defect_text_extraction",
        prompt_version="2.0.0",
        prompt_content_hash="b" * 64,
        input_schema_version="2.0",
        output_schema_version="2.0",
        precision="awq-int4",
        max_context_tokens=8192,
        max_num_sequences=1,
        gpu_memory_utilization=0.9,
        kv_cache_dtype="auto",
        qualification_dataset_digest=digest,
        qualification_result_digest=digest,
        candidate_matrix_digest=digest,
        candidate_assessment_digest=digest,
        qualified_at=NOW,
    )


def _signed(private_key: Ed25519PrivateKey) -> SignedLLMReleaseManifest:
    manifest = _manifest()
    return SignedLLMReleaseManifest(
        manifest=manifest,
        signing_key_id="pilot-release-key-1",
        signature_base64=base64.b64encode(private_key.sign(manifest.canonical_bytes())).decode(),
    )


def _verifier(private_key: Ed25519PrivateKey) -> Ed25519ModelReleaseSignatureVerifier:
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    return Ed25519ModelReleaseSignatureVerifier.from_pem_bytes(
        public_key_pem=public_pem,
        expected_key_id="pilot-release-key-1",
    )


def _identity(manifest: LLMReleaseManifest) -> RuntimeLLMIdentity:
    return RuntimeLLMIdentity.model_validate(
        {key: getattr(manifest, key) for key in RuntimeLLMIdentity.model_fields}
    )


class ActiveRepository:
    def __init__(self, active: ActiveLLMRelease | None) -> None:
        self.active = active

    def get_active(self, **_: object) -> ActiveLLMRelease | None:
        return self.active


def _active(signed: SignedLLMReleaseManifest) -> ActiveLLMRelease:
    release = RegisteredLLMRelease(
        id="release-1",
        tenant_id="tenant-1",
        signed_manifest=signed,
        registered_by="admin-1",
        registered_at=NOW,
    )
    activation = ModelActivationEvent(
        id="activation-1",
        tenant_id="tenant-1",
        task=signed.manifest.task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_release_id=release.id,
        activated_by="admin-1",
        reason="Qualified on the target RTX 4090 host.",
        idempotency_key="activate-1",
        request_hash="c" * 64,
        activated_at=NOW,
    )
    return ActiveLLMRelease(release=release, activation=activation)


def test_ed25519_verifier_accepts_canonical_manifest_and_rejects_tampering() -> None:
    private_key = Ed25519PrivateKey.generate()
    signed = _signed(private_key)
    verifier = _verifier(private_key)

    assert verifier.verify(signed) is True
    tampered = signed.model_copy(
        update={"manifest": signed.manifest.model_copy(update={"model_version": "tampered"})}
    )
    assert verifier.verify(tampered) is False
    assert verifier.verify(signed.model_copy(update={"signing_key_id": "other-key"})) is False


def test_worker_guard_requires_active_signed_exact_runtime_identity() -> None:
    private_key = Ed25519PrivateKey.generate()
    signed = _signed(private_key)
    active = _active(signed)
    guard = RequireActiveModelRelease(
        repository=ActiveRepository(active),  # type: ignore[arg-type]
        signature_verifier=_verifier(private_key),
        runtime_identity=_identity(signed.manifest),
    )

    assert (
        guard.execute(
            tenant_id="tenant-1",
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )
        == active
    )

    missing = RequireActiveModelRelease(
        repository=ActiveRepository(None),  # type: ignore[arg-type]
        signature_verifier=_verifier(private_key),
        runtime_identity=_identity(signed.manifest),
    )
    with pytest.raises(ActiveModelReleaseRequiredError):
        missing.execute(
            tenant_id="tenant-1",
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )

    mismatch = RequireActiveModelRelease(
        repository=ActiveRepository(active),  # type: ignore[arg-type]
        signature_verifier=_verifier(private_key),
        runtime_identity=_identity(signed.manifest).model_copy(
            update={"runtime_image_digest": "sha256:" + "d" * 64}
        ),
    )
    with pytest.raises(ModelReleaseIdentityMismatchError):
        mismatch.execute(
            tenant_id="tenant-1",
            execution_mode=AnalysisExecutionMode.PRIMARY,
        )
