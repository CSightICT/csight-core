"""Fail-closed composition for immutable text-extraction model routes."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.model_activation import SQLAlchemyModelActivationRepository
from app.adapters.persistence.model_routing import SQLAlchemyModelRoutePlanRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.security.model_release_signatures import (
    Ed25519ModelReleaseSignatureVerifier,
)
from app.application.model_routing import (
    ResolveActiveModelRoutePlan,
    ResolvePinnedModelRoutePlan,
)
from app.bootstrap.model_activation import build_runtime_llm_identity
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
from app.domains.product_defect_cs.prompts import (
    GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
    POLICY_QUERY_BUILDER_PROMPT_V1_1,
)
from app.platform.analysis.prompts import PromptManifest
from app.platform.model_activation import ModelReleaseTask
from app.platform.model_routing import ModelRouteDeploymentIdentity


class ModelRoutingConfigurationError(RuntimeError):
    """Raised without configuration values when route enforcement is unsafe."""


def build_active_model_route_resolver(
    settings: Settings,
) -> ResolveActiveModelRoutePlan | None:
    """Build the API resolver that snapshots the active v2 route on new requests."""

    if not settings.model_route_enforcement:
        return None
    _require_route_process(settings, role="api")
    route_repository, activation_repository, verifier = _dependencies(settings)
    return ResolveActiveModelRoutePlan(
        route_repository=route_repository,
        activation_repository=activation_repository,
        signature_verifier=verifier,
    )


def build_pinned_model_route_guard(
    settings: Settings,
    *,
    prompt: PromptManifest | None = None,
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> ResolvePinnedModelRoutePlan | None:
    """Build the model Worker guard for a stage's historical v2 route."""

    if not settings.model_route_enforcement:
        return None
    _require_route_process(settings, role="worker")
    task_runtime = settings.llm_task_runtimes.get(task)
    deployment_id = (
        task_runtime.deployment_id
        if task_runtime is not None
        else settings.model_route_deployment_id
    )
    if deployment_id is None:
        raise ModelRoutingConfigurationError(
            "MODEL_ROUTE_DEPLOYMENT_ID is required for the model Worker"
        )
    route_repository, activation_repository, verifier = _dependencies(settings)
    return ResolvePinnedModelRoutePlan(
        route_repository=route_repository,
        activation_repository=activation_repository,
        signature_verifier=verifier,
        deployment_identity=ModelRouteDeploymentIdentity(
            deployment_id=deployment_id,
            runtime_identity=build_runtime_llm_identity(settings, prompt, task),
        ),
    )


def validate_model_route_worker_startup(settings: Settings) -> None:
    """Reject an enforced Worker before Celery starts when its guard cannot compose."""

    if settings.model_route_enforcement:
        for task, prompt in (
            (
                ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
                PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
            ),
            (ModelReleaseTask.POLICY_QUERY_BUILDER_V1, POLICY_QUERY_BUILDER_PROMPT_V1_1),
            (
                ModelReleaseTask.GROUNDED_POLICY_EXPLANATION_V1,
                GROUNDED_POLICY_EXPLANATION_PROMPT_V1_1,
            ),
        ):
            guard = build_pinned_model_route_guard(settings, prompt=prompt, task=task)
            if guard is None:
                raise ModelRoutingConfigurationError("model route guard was not composed")


def _require_route_process(settings: Settings, *, role: str) -> None:
    if not settings.model_release_enforcement:
        raise ModelRoutingConfigurationError(
            "model route enforcement requires signed model release enforcement"
        )
    if settings.database_runtime_role != role or not settings.database_rls_required:
        raise ModelRoutingConfigurationError(
            f"model route enforcement requires the RLS-protected {role} database role"
        )


def _dependencies(
    settings: Settings,
) -> tuple[
    SQLAlchemyModelRoutePlanRepository,
    SQLAlchemyModelActivationRepository,
    Ed25519ModelReleaseSignatureVerifier,
]:
    if settings.database_url_value is None:
        raise ModelRoutingConfigurationError("DATABASE_URL is required for model routing")
    key_file = settings.model_release_signing_public_key_file
    key_id = settings.model_release_signing_key_id
    if key_file is None or key_id is None:
        raise ModelRoutingConfigurationError(
            "model release verification key is required for model routing"
        )
    session_factory = create_session_factory(get_engine(settings))
    return (
        SQLAlchemyModelRoutePlanRepository(session_factory),
        SQLAlchemyModelActivationRepository(session_factory),
        Ed25519ModelReleaseSignatureVerifier.from_file(
            public_key_file=key_file,
            expected_key_id=key_id,
        ),
    )


__all__ = [
    "ModelRoutingConfigurationError",
    "build_active_model_route_resolver",
    "build_pinned_model_route_guard",
    "validate_model_route_worker_startup",
]
