"""Admin-only signed model registration, append-only activation, and Worker authorization."""

from __future__ import annotations

import hashlib
import json

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.errors import ForbiddenError, ValidationError
from app.platform.model_activation import (
    ActiveLLMRelease,
    ActiveModelReleaseRequiredError,
    ModelActivationEvent,
    ModelActivationResult,
    ModelReleaseIdentityMismatchError,
    ModelReleaseNotFoundError,
    ModelReleaseRegistrationResult,
    ModelReleaseSignatureInvalidError,
    ModelReleaseTask,
    RuntimeLLMIdentity,
    SignedLLMReleaseManifest,
)
from app.platform.tenant import Principal, Role
from app.ports.model_activation import (
    ModelActivationRepository,
    ModelReleaseSignatureVerifier,
)
from app.ports.runtime import Clock, IdGenerator


class RegisterSignedModelRelease:
    def __init__(
        self,
        *,
        repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._repository = repository
        self._signature_verifier = signature_verifier
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        principal: Principal,
        value: SignedLLMReleaseManifest,
    ) -> ModelReleaseRegistrationResult:
        _require_admin(principal)
        if not self._signature_verifier.verify(value):
            raise ModelReleaseSignatureInvalidError()
        release, idempotent_replay = self._repository.register_release(
            tenant_id=principal.tenant_id,
            release_id=self._id_generator.new_id(),
            value=value,
            registered_by=principal.user_id,
            registered_at=self._clock.now(),
        )
        return ModelReleaseRegistrationResult(
            release=release,
            idempotent_replay=idempotent_replay,
        )


class ActivateSignedModelRelease:
    def __init__(
        self,
        *,
        repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._repository = repository
        self._signature_verifier = signature_verifier
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        principal: Principal,
        release_id: str,
        execution_mode: AnalysisExecutionMode,
        expected_current_activation_id: str | None,
        reason: str,
        idempotency_key: str,
    ) -> ModelActivationResult:
        _require_admin(principal)
        normalized_reason = reason.strip()
        normalized_key = idempotency_key.strip()
        if not 1 <= len(normalized_reason) <= 1000:
            raise ValidationError(
                "Model activation reason must contain between 1 and 1000 characters."
            )
        if not 1 <= len(normalized_key) <= 255:
            raise ValidationError("Idempotency-Key must contain between 1 and 255 characters.")
        release = self._repository.get_release(
            tenant_id=principal.tenant_id,
            release_id=release_id,
        )
        if release is None:
            raise ModelReleaseNotFoundError()
        if not self._signature_verifier.verify(release.signed_manifest):
            raise ModelReleaseSignatureInvalidError()
        task = release.signed_manifest.manifest.task
        current = self._repository.get_active(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        previous_id = current.activation.id if current is not None else None
        request_hash = _activation_request_hash(
            release_id=release_id,
            execution_mode=execution_mode,
            expected_current_activation_id=expected_current_activation_id,
            reason=normalized_reason,
        )
        event = ModelActivationEvent(
            id=self._id_generator.new_id(),
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
            model_release_id=release_id,
            previous_activation_id=previous_id,
            activated_by=principal.user_id,
            reason=normalized_reason,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            activated_at=self._clock.now(),
        )
        activation, idempotent_replay = self._repository.activate(
            event=event,
            expected_current_activation_id=expected_current_activation_id,
        )
        return ModelActivationResult(
            activation=activation,
            idempotent_replay=idempotent_replay,
        )


class GetActiveModelRelease:
    def __init__(self, repository: ModelActivationRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ActiveLLMRelease | None:
        _require_admin(principal)
        return self._repository.get_active(
            tenant_id=principal.tenant_id,
            task=task,
            execution_mode=execution_mode,
        )


class RequireActiveModelRelease:
    """Fail before a model call when Worker identity is not the active signed release."""

    def __init__(
        self,
        *,
        repository: ModelActivationRepository,
        signature_verifier: ModelReleaseSignatureVerifier,
        runtime_identity: RuntimeLLMIdentity,
    ) -> None:
        self._repository = repository
        self._signature_verifier = signature_verifier
        self._runtime_identity = runtime_identity

    @property
    def runtime_identity(self) -> RuntimeLLMIdentity:
        return self._runtime_identity

    def execute(
        self,
        *,
        tenant_id: str,
        execution_mode: AnalysisExecutionMode,
        task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
    ) -> ActiveLLMRelease:
        active = self._repository.get_active(
            tenant_id=tenant_id,
            task=task,
            execution_mode=execution_mode,
        )
        if active is None:
            raise ActiveModelReleaseRequiredError()
        signed = active.release.signed_manifest
        if not self._signature_verifier.verify(signed):
            raise ModelReleaseSignatureInvalidError()
        manifest = signed.manifest
        expected = {
            "served_model_name": manifest.served_model_name,
            "model_version": manifest.model_version,
            "artifact_revision": manifest.artifact_revision,
            "artifact_content_digest": manifest.artifact_content_digest,
            "runtime_image_digest": manifest.runtime_image_digest,
            "dependency_lock_digest": manifest.dependency_lock_digest,
            "sbom_digest": manifest.sbom_digest,
            "prompt_name": manifest.prompt_name,
            "prompt_version": manifest.prompt_version,
            "prompt_content_hash": manifest.prompt_content_hash,
            "input_schema_version": manifest.input_schema_version,
            "output_schema_version": manifest.output_schema_version,
        }
        if self._runtime_identity.model_dump(mode="python") != expected:
            raise ModelReleaseIdentityMismatchError()
        return active


def _require_admin(principal: Principal) -> None:
    if Role.ADMIN not in principal.roles:
        raise ForbiddenError()


def _activation_request_hash(
    *,
    release_id: str,
    execution_mode: AnalysisExecutionMode,
    expected_current_activation_id: str | None,
    reason: str,
) -> str:
    encoded = json.dumps(
        {
            "release_id": release_id,
            "execution_mode": execution_mode.value,
            "expected_current_activation_id": expected_current_activation_id,
            "reason": reason,
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ActivateSignedModelRelease",
    "GetActiveModelRelease",
    "RegisterSignedModelRelease",
    "RequireActiveModelRelease",
]
