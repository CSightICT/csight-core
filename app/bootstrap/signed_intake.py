"""Composition root for deployment-authorized Ed25519 Case intake."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepositoryFactoryAdapter
from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.unit_of_work import create_case_unit_of_work_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.security.signed_intake_signatures import (
    ConfiguredSignedIntakeSourceRegistry,
    Ed25519SignedIntakeSignatureVerifier,
    load_ed25519_public_key_file,
)
from app.application.cases import CreateSignedIntakeCase
from app.application.signed_intake import AuthenticateSignedIntake
from app.bootstrap.settings import Settings
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.platform.signed_intake import SignedIntakeSource


class SignedIntakeConfigurationError(RuntimeError):
    """Raised without key material when signed intake cannot start safely."""


def signed_intake_is_configured(settings: Settings) -> bool:
    return settings.signed_intake_is_configured


def build_signed_intake_services(settings: Settings) -> SignedIntakeServiceContainer:
    missing = settings.signed_intake_configuration_missing
    if missing:
        raise SignedIntakeConfigurationError(
            f"Signed intake configuration is incomplete: {', '.join(missing)}"
        )

    retention_version = settings.sensitive_payload_retention_policy_version_value
    retention_days = settings.sensitive_payload_retention_days_value
    if retention_version is None or retention_days is None:
        raise SignedIntakeConfigurationError(
            "Signed intake requires an explicit sensitive payload retention policy"
        )

    sources: dict[str, SignedIntakeSource] = {}
    public_keys = {}
    for key_id, configured in settings.signed_intake_sources.items():
        sources[key_id] = SignedIntakeSource(
            key_id=key_id,
            source_id=configured.source_id,
            tenant_id=str(configured.tenant_id),
            actor_user_id=str(configured.actor_user_id),
            provenance=configured.provenance,
        )
        public_keys[key_id] = load_ed25519_public_key_file(configured.public_key_file)

    engine = get_engine(settings)
    session_factory = create_session_factory(engine)
    clock = UtcClock()
    uow_factory = create_case_unit_of_work_factory(
        engine,
        sensitive_payload_retention_policy_version=retention_version,
        sensitive_payload_retention_days=retention_days,
    )
    return SignedIntakeServiceContainer(
        authenticate=AuthenticateSignedIntake(
            sources=ConfiguredSignedIntakeSourceRegistry(sources),
            signatures=Ed25519SignedIntakeSignatureVerifier(public_keys),
            identities=SQLAlchemyIdentityRepositoryFactoryAdapter(session_factory),
            clock=clock,
            allowed_clock_skew=timedelta(seconds=settings.signed_intake_clock_skew_seconds),
        ),
        create_case=CreateSignedIntakeCase(
            uow_factory=uow_factory,
            clock=clock,
            id_generator=Uuid4Generator(),
        ),
        max_body_bytes=settings.signed_intake_max_body_bytes,
    )


__all__ = [
    "SignedIntakeConfigurationError",
    "build_signed_intake_services",
    "signed_intake_is_configured",
]
