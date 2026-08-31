"""Composition and fail-closed startup validation for signed model releases."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.model_activation import SQLAlchemyModelActivationRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.security.model_release_signatures import (
    Ed25519ModelReleaseSignatureVerifier,
)
from app.application.model_activation import (
    ActivateSignedModelRelease,
    GetActiveModelRelease,
    RegisterSignedModelRelease,
    RequireActiveModelRelease,
)
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.platform.model_activation import RuntimeLLMIdentity


class ModelActivationConfigurationError(RuntimeError):
    """Raised without secret or key material when release gating is incomplete."""


def model_activation_is_configured(settings: Settings) -> bool:
    return bool(
        settings.database_url_value
        and settings.model_release_signing_public_key_file
        and settings.model_release_signing_key_id
    )


def build_model_activation_services(
    settings: Settings,
) -> tuple[RegisterSignedModelRelease, ActivateSignedModelRelease, GetActiveModelRelease]:
    repository = _repository(settings)
    verifier = _verifier(settings)
    clock = UtcClock()
    generator = Uuid4Generator()
    return (
        RegisterSignedModelRelease(
            repository=repository,
            signature_verifier=verifier,
            clock=clock,
            id_generator=generator,
        ),
        ActivateSignedModelRelease(
            repository=repository,
            signature_verifier=verifier,
            clock=clock,
            id_generator=generator,
        ),
        GetActiveModelRelease(repository),
    )


def build_model_release_guard(settings: Settings) -> RequireActiveModelRelease | None:
    if not settings.model_release_enforcement:
        return None
    return RequireActiveModelRelease(
        repository=_repository(settings),
        signature_verifier=_verifier(settings),
        runtime_identity=build_runtime_llm_identity(settings),
    )


def build_runtime_llm_identity(settings: Settings) -> RuntimeLLMIdentity:
    """Build the exact v2 runtime identity shared by release and route guards."""

    prompt = PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
    required = (
        settings.llm_model_revision,
        settings.llm_artifact_content_digest,
        settings.llm_runtime_image_digest,
        settings.llm_dependency_lock_digest,
        settings.llm_sbom_digest,
    )
    if not all(required):
        raise ModelActivationConfigurationError("signed model runtime identity is incomplete")
    return RuntimeLLMIdentity(
        served_model_name=settings.llm_model_id,
        model_version=settings.llm_model_version,
        artifact_revision=str(required[0]),
        artifact_content_digest=str(required[1]),
        runtime_image_digest=str(required[2]),
        dependency_lock_digest=str(required[3]),
        sbom_digest=str(required[4]),
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_content_hash=prompt.content_hash,
        input_schema_version=prompt.input_schema_version,
        output_schema_version=prompt.output_schema_version,
    )


def validate_model_release_worker_startup(settings: Settings) -> None:
    if settings.model_release_enforcement:
        if settings.database_runtime_role != "worker" or not settings.database_rls_required:
            raise ModelActivationConfigurationError(
                "signed model enforcement requires the RLS-protected Worker database role"
            )
        build_model_release_guard(settings)


def _repository(settings: Settings) -> SQLAlchemyModelActivationRepository:
    if settings.database_url_value is None:
        raise ModelActivationConfigurationError("DATABASE_URL is required for model activation")
    return SQLAlchemyModelActivationRepository(create_session_factory(get_engine(settings)))


def _verifier(settings: Settings) -> Ed25519ModelReleaseSignatureVerifier:
    key_file = settings.model_release_signing_public_key_file
    key_id = settings.model_release_signing_key_id
    if key_file is None or key_id is None:
        raise ModelActivationConfigurationError("model release verification key is not configured")
    return Ed25519ModelReleaseSignatureVerifier.from_file(
        public_key_file=key_file,
        expected_key_id=key_id,
    )


__all__ = [
    "ModelActivationConfigurationError",
    "build_model_activation_services",
    "build_model_release_guard",
    "build_runtime_llm_identity",
    "model_activation_is_configured",
    "validate_model_release_worker_startup",
]
