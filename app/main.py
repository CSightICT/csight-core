"""FastAPI application factory and ASGI entrypoint."""

from fastapi import FastAPI

from app.bootstrap.logging import configure_logging
from app.bootstrap.settings import Settings, get_settings
from app.bootstrap.sprint1 import build_sprint1_services, sprint1_is_configured
from app.bootstrap.sprint2 import build_sprint2_services, sprint2_is_configured
from app.bootstrap.sprint4b import build_sprint4b_services, sprint4b_is_configured
from app.bootstrap.sprint4c2 import build_sprint4c2_services, sprint4c2_is_configured
from app.interface.http import (
    register_correlation_id_middleware,
    register_evidence_upload_body_limit_middleware,
    register_exception_handlers,
)
from app.interface.http.routers import (
    analysis_router,
    auth_router,
    cases_router,
    evidence_router,
    health_router,
    policy_query_runs_router,
    policy_retrieval_router,
    system_router,
)
from app.interface.http.services import (
    Sprint1ServiceContainer,
    Sprint2ServiceContainer,
    Sprint4BServiceContainer,
    Sprint4C2ServiceContainer,
)
from app.ports.readiness import ReadinessService


def create_app(
    settings: Settings | None = None,
    *,
    readiness_service: ReadinessService | None = None,
    sprint1_services: Sprint1ServiceContainer | None = None,
    sprint2_services: Sprint2ServiceContainer | None = None,
    sprint4b_services: Sprint4BServiceContainer | None = None,
    sprint4c2_services: Sprint4C2ServiceContainer | None = None,
) -> FastAPI:
    """Create an independently configurable API instance for deployment or tests."""

    resolved_settings = settings or get_settings()
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

    # Register the body cap first so the correlation middleware remains outermost
    # and every early 413 response carries the same trace identifier contract.
    register_evidence_upload_body_limit_middleware(
        application,
        max_upload_bytes=resolved_settings.max_upload_bytes,
    )
    register_correlation_id_middleware(application)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(system_router)
    application.include_router(auth_router)
    application.include_router(cases_router)
    application.include_router(evidence_router)
    application.include_router(analysis_router)
    application.include_router(policy_retrieval_router)
    application.include_router(policy_query_runs_router)
    return application


app = create_app()
