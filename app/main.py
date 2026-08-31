"""FastAPI application factory and ASGI entrypoint."""

from fastapi import FastAPI

from app.adapters.telemetry import TelemetryRuntime
from app.bootstrap.logging import configure_logging
from app.bootstrap.oidc import (
    OidcConfigurationError,
    OidcRuntime,
    build_oidc_runtime,
    oidc_is_configured,
)
from app.bootstrap.operations import build_operations_services, operations_is_configured
from app.bootstrap.operator_read import (
    build_operator_read_services,
    operator_read_is_configured,
)
from app.bootstrap.poc_reporting import (
    build_poc_reporting_services,
    poc_reporting_is_configured,
)
from app.bootstrap.settings import Settings, get_settings
from app.bootstrap.signed_intake import build_signed_intake_services
from app.bootstrap.sprint1 import build_sprint1_services, sprint1_is_configured
from app.bootstrap.sprint2 import build_sprint2_services, sprint2_is_configured
from app.bootstrap.sprint4b import build_sprint4b_services, sprint4b_is_configured
from app.bootstrap.sprint4c2 import build_sprint4c2_services, sprint4c2_is_configured
from app.bootstrap.sprint4c3a import build_sprint4c3a_services, sprint4c3a_is_configured
from app.bootstrap.sprint5a import build_sprint5a_services, sprint5a_is_configured
from app.bootstrap.sprint5b import build_sprint5b_services, sprint5b_is_configured
from app.bootstrap.sprint5c import build_sprint5c_services, sprint5c_is_configured
from app.bootstrap.telemetry import build_process_telemetry
from app.interface.http import (
    register_correlation_id_middleware,
    register_evidence_upload_body_limit_middleware,
    register_exception_handlers,
)
from app.interface.http.oidc_router import create_auth_capabilities_router, create_oidc_router
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.operator_read_services import OperatorReadServiceContainer
from app.interface.http.poc_reporting_services import PocReportingServiceContainer
from app.interface.http.routers import (
    analysis_router,
    auth_router,
    case_resolution_router,
    cases_router,
    create_signed_intake_router,
    evidence_router,
    grounding_router,
    health_router,
    human_review_assignee_router,
    human_review_case_router,
    human_review_router,
    legacy_password_router,
    operations_router,
    operator_read_router,
    poc_reporting_router,
    policy_evaluations_router,
    policy_query_runs_router,
    policy_retrieval_router,
    system_router,
)
from app.interface.http.services import (
    Sprint1ServiceContainer,
    Sprint2ServiceContainer,
    Sprint4BServiceContainer,
    Sprint4C2ServiceContainer,
    Sprint4C3AServiceContainer,
    Sprint5AServiceContainer,
    Sprint5BServiceContainer,
    Sprint5CServiceContainer,
)
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.interface.http.telemetry import register_http_telemetry_middleware
from app.ports.readiness import ReadinessService


def create_app(
    settings: Settings | None = None,
    *,
    readiness_service: ReadinessService | None = None,
    sprint1_services: Sprint1ServiceContainer | None = None,
    sprint2_services: Sprint2ServiceContainer | None = None,
    sprint4b_services: Sprint4BServiceContainer | None = None,
    sprint4c2_services: Sprint4C2ServiceContainer | None = None,
    sprint4c3a_services: Sprint4C3AServiceContainer | None = None,
    sprint5a_services: Sprint5AServiceContainer | None = None,
    sprint5b_services: Sprint5BServiceContainer | None = None,
    sprint5c_services: Sprint5CServiceContainer | None = None,
    poc_reporting_services: PocReportingServiceContainer | None = None,
    operator_read_services: OperatorReadServiceContainer | None = None,
    operations_services: OperationsServiceContainer | None = None,
    oidc_runtime: OidcRuntime | None = None,
    telemetry_runtime: TelemetryRuntime | None = None,
    signed_intake_services: SignedIntakeServiceContainer | None = None,
) -> FastAPI:
    """Create an independently configurable API instance for deployment or tests."""

    resolved_settings = settings or get_settings()
    if (
        resolved_settings.environment not in {"local", "test"}
        and oidc_runtime is None
        and not oidc_is_configured(resolved_settings)
    ):
        raise OidcConfigurationError(
            "OIDC configuration is required before a non-local API can start"
        )
    configure_logging(resolved_settings.log_level)
    resolved_sprint1_services = sprint1_services
    if resolved_sprint1_services is None and sprint1_is_configured(resolved_settings):
        resolved_sprint1_services = build_sprint1_services(resolved_settings)
    resolved_sprint2_services = sprint2_services
    if resolved_sprint2_services is None and sprint2_is_configured(resolved_settings):
        resolved_sprint2_services = build_sprint2_services(resolved_settings)
    resolved_sprint4b_services = sprint4b_services
    if resolved_sprint4b_services is None and sprint4b_is_configured(resolved_settings):
        resolved_sprint4b_services = build_sprint4b_services(resolved_settings)
    resolved_sprint4c2_services = sprint4c2_services
    if resolved_sprint4c2_services is None and sprint4c2_is_configured(resolved_settings):
        resolved_sprint4c2_services = build_sprint4c2_services(resolved_settings)
    resolved_sprint4c3a_services = sprint4c3a_services
    if resolved_sprint4c3a_services is None and sprint4c3a_is_configured(resolved_settings):
        resolved_sprint4c3a_services = build_sprint4c3a_services(resolved_settings)
    resolved_sprint5a_services = sprint5a_services
    if resolved_sprint5a_services is None and sprint5a_is_configured(resolved_settings):
        resolved_sprint5a_services = build_sprint5a_services(resolved_settings)
    resolved_sprint5b_services = sprint5b_services
    if resolved_sprint5b_services is None and sprint5b_is_configured(resolved_settings):
        resolved_sprint5b_services = build_sprint5b_services(resolved_settings)
    resolved_sprint5c_services = sprint5c_services
    if resolved_sprint5c_services is None and sprint5c_is_configured(resolved_settings):
        resolved_sprint5c_services = build_sprint5c_services(resolved_settings)
    resolved_poc_reporting_services = poc_reporting_services
    if resolved_poc_reporting_services is None and poc_reporting_is_configured(resolved_settings):
        resolved_poc_reporting_services = build_poc_reporting_services(resolved_settings)
    resolved_operator_read_services = operator_read_services
    if resolved_operator_read_services is None and operator_read_is_configured(resolved_settings):
        resolved_operator_read_services = build_operator_read_services(resolved_settings)
    resolved_operations_services = operations_services
    if resolved_operations_services is None and operations_is_configured(resolved_settings):
        resolved_operations_services = build_operations_services(resolved_settings)
    resolved_oidc_runtime = oidc_runtime
    if resolved_oidc_runtime is None and oidc_is_configured(resolved_settings):
        resolved_oidc_runtime = build_oidc_runtime(resolved_settings)
    resolved_telemetry_runtime = telemetry_runtime or build_process_telemetry(resolved_settings)
    resolved_signed_intake_services = signed_intake_services
    if resolved_signed_intake_services is None and resolved_settings.signed_intake_enabled:
        resolved_signed_intake_services = build_signed_intake_services(resolved_settings)

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
    )
    application.state.settings = resolved_settings
    application.state.readiness_service = readiness_service
    application.state.sprint1_services = resolved_sprint1_services
    application.state.sprint2_services = resolved_sprint2_services
    application.state.sprint4b_services = resolved_sprint4b_services
    application.state.sprint4c2_services = resolved_sprint4c2_services
    application.state.sprint4c3a_services = resolved_sprint4c3a_services
    application.state.sprint5a_services = resolved_sprint5a_services
    application.state.sprint5b_services = resolved_sprint5b_services
    application.state.sprint5c_services = resolved_sprint5c_services
    application.state.poc_reporting_services = resolved_poc_reporting_services
    application.state.operator_read_services = resolved_operator_read_services
    application.state.operations_services = resolved_operations_services
    application.state.signed_intake_services = resolved_signed_intake_services
    application.state.telemetry_runtime = resolved_telemetry_runtime
    application.state.oidc_service = (
        resolved_oidc_runtime.service if resolved_oidc_runtime is not None else None
    )
    application.state.oidc_cookie_configuration = (
        resolved_oidc_runtime.cookie if resolved_oidc_runtime is not None else None
    )
    application.state.legacy_password_auth_enabled = resolved_settings.legacy_password_enabled

    # Register the body cap and telemetry first so correlation remains outermost.
    # This ensures every instrumented request and early 413 response shares the
    # normalized correlation identifier.
    register_evidence_upload_body_limit_middleware(
        application,
        max_upload_bytes=resolved_settings.max_upload_bytes,
    )
    register_http_telemetry_middleware(
        application,
        runtime=resolved_telemetry_runtime,
    )
    register_correlation_id_middleware(application)
    register_exception_handlers(application)
    if resolved_telemetry_runtime.enabled:
        application.router.add_event_handler("shutdown", resolved_telemetry_runtime.shutdown)
    application.include_router(health_router)
    application.include_router(system_router)
    application.include_router(auth_router)
    if resolved_settings.legacy_password_enabled:
        application.include_router(legacy_password_router)
    application.include_router(
        create_auth_capabilities_router(
            oidc_enabled=resolved_oidc_runtime is not None,
            legacy_password_enabled=(
                resolved_settings.legacy_password_enabled and resolved_sprint1_services is not None
            ),
        )
    )
    if resolved_oidc_runtime is not None:
        application.include_router(
            create_oidc_router(
                service=resolved_oidc_runtime.service,
                cookie=resolved_oidc_runtime.cookie,
            )
        )
    application.include_router(cases_router)
    if resolved_signed_intake_services is not None:
        application.include_router(create_signed_intake_router(resolved_signed_intake_services))
    application.include_router(case_resolution_router)
    application.include_router(poc_reporting_router)
    application.include_router(evidence_router)
    application.include_router(analysis_router)
    application.include_router(policy_retrieval_router)
    application.include_router(policy_query_runs_router)
    application.include_router(grounding_router)
    application.include_router(policy_evaluations_router)
    application.include_router(human_review_router)
    application.include_router(human_review_case_router)
    application.include_router(human_review_assignee_router)
    application.include_router(operator_read_router)
    application.include_router(operations_router)
    return application


app = create_app()
