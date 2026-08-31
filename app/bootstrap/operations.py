"""Composition root for aggregate operations reads."""

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.failure_recovery import SQLAlchemyOperationalFailureRepository
from app.adapters.persistence.model_activation import SQLAlchemyModelActivationRepository
from app.adapters.persistence.model_routing import SQLAlchemyModelRoutePlanRepository
from app.adapters.persistence.onboarding_readiness import (
    SQLAlchemyOnboardingReadinessRepository,
)
from app.adapters.persistence.operations import SQLAlchemyOperationsReadRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.pilot_readiness import JsonPilotQualificationEvidenceRepository
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.security.model_release_signatures import (
    Ed25519ModelReleaseSignatureVerifier,
)
from app.application.model_activation import (
    ActivateSignedModelRelease,
    GetActiveModelRelease,
    RegisterSignedModelRelease,
)
from app.application.model_routing import (
    ActivateModelRoutePlan,
    GetActiveModelRoutePlan,
    ResolveActiveModelRoutePlan,
)
from app.application.onboarding_readiness import (
    GetOnboardingReadiness,
    OnboardingReadinessConfiguration,
)
from app.application.operations import (
    GetOperationsFailures,
    GetOperationsOverview,
    ListOperationalFailures,
)
from app.application.pilot_readiness import GetPilotReadiness
from app.bootstrap.model_activation import model_activation_is_configured
from app.bootstrap.settings import Settings
from app.interface.http.operations_services import OperationsServiceContainer


def operations_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def build_operations_services(settings: Settings) -> OperationsServiceContainer:
    session_factory = create_session_factory(get_engine(settings))
    repository = SQLAlchemyOperationsReadRepository(session_factory)
    failure_repository = SQLAlchemyOperationalFailureRepository(session_factory)
    clock = UtcClock()
    onboarding_repository = SQLAlchemyOnboardingReadinessRepository(session_factory)
    activation_services: tuple[
        RegisterSignedModelRelease | None,
        ActivateSignedModelRelease | None,
        GetActiveModelRelease | None,
        ActivateModelRoutePlan | None,
        GetActiveModelRoutePlan | None,
    ] = (None, None, None, None, None)
    if model_activation_is_configured(settings):
        key_file = settings.model_release_signing_public_key_file
        key_id = settings.model_release_signing_key_id
        assert key_file is not None and key_id is not None
        activation_repository = SQLAlchemyModelActivationRepository(session_factory)
        verifier = Ed25519ModelReleaseSignatureVerifier.from_file(
            public_key_file=key_file,
            expected_key_id=key_id,
        )
        generator = Uuid4Generator()
        register_release = RegisterSignedModelRelease(
            repository=activation_repository,
            signature_verifier=verifier,
            clock=clock,
            id_generator=generator,
        )
        activate_release = ActivateSignedModelRelease(
            repository=activation_repository,
            signature_verifier=verifier,
            clock=clock,
            id_generator=generator,
        )
        get_active_release = GetActiveModelRelease(activation_repository)
        route_repository = SQLAlchemyModelRoutePlanRepository(session_factory)
        route_resolver = ResolveActiveModelRoutePlan(
            route_repository=route_repository,
            activation_repository=activation_repository,
            signature_verifier=verifier,
        )
        activation_services = (
            register_release,
            activate_release,
            get_active_release,
            ActivateModelRoutePlan(
                route_repository=route_repository,
                activation_repository=activation_repository,
                signature_verifier=verifier,
                clock=clock,
                id_generator=generator,
            ),
            GetActiveModelRoutePlan(route_resolver),
        )
    onboarding_readiness = GetOnboardingReadiness(
        repository=onboarding_repository,
        configuration=onboarding_readiness_configuration(settings),
        clock=clock,
    )
    return OperationsServiceContainer(
        get_overview=GetOperationsOverview(repository, clock),
        get_failures=GetOperationsFailures(repository, clock),
        list_failure_records=ListOperationalFailures(failure_repository, clock),
        # Recovery mutation code remains available for qualification tests, but
        # the pilot runtime is intentionally read-only until every pipeline can
        # prove that cancel terminalizes the source before recording a resolution.
        replay_failure=None,
        cancel_failure=None,
        register_model_release=activation_services[0],
        activate_model_release=activation_services[1],
        get_active_model_release=activation_services[2],
        activate_model_route=activation_services[3],
        get_active_model_route=activation_services[4],
        get_onboarding_readiness=onboarding_readiness,
        get_pilot_readiness=GetPilotReadiness(
            onboarding=onboarding_readiness,
            evidence_repository=JsonPilotQualificationEvidenceRepository(
                getattr(settings, "pilot_qualification_evidence_file", None)
            ),
            clock=clock,
            evidence_max_age=timedelta(
                hours=getattr(settings, "pilot_qualification_evidence_max_age_hours", 24)
            ),
        ),
    )


def onboarding_readiness_configuration(
    settings: Settings,
) -> OnboardingReadinessConfiguration:
    actor_ids_by_tenant: dict[str, list[str]] = {}
    if settings.signed_intake_is_configured:
        for source in settings.signed_intake_sources.values():
            actor_ids_by_tenant.setdefault(str(source.tenant_id), []).append(
                str(source.actor_user_id)
            )

    oidc_tenant_slugs = (
        frozenset(target.tenant_slug for target in settings.oidc_group_mappings.values())
        if settings.oidc_is_configured
        else frozenset()
    )
    return OnboardingReadinessConfiguration(
        signed_actor_ids_by_tenant={
            tenant_id: tuple(dict.fromkeys(actor_ids))
            for tenant_id, actor_ids in actor_ids_by_tenant.items()
        },
        retention_policy_explicit=(
            settings.sensitive_payload_retention_policy_version is not None
            and settings.sensitive_payload_retention_days is not None
        ),
        retention_automation_tenant_id=(
            str(settings.privacy_lifecycle_tenant_id)
            if settings.privacy_lifecycle_automation_enabled
            and settings.privacy_lifecycle_tenant_id is not None
            else None
        ),
        oidc_tenant_slugs=oidc_tenant_slugs,
        model_route_runtime_complete=getattr(settings, "model_route_enforcement", False),
    )


__all__ = [
    "build_operations_services",
    "onboarding_readiness_configuration",
    "operations_is_configured",
]
