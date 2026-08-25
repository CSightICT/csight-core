"""FastAPI application factory and ASGI entrypoint."""

from fastapi import FastAPI

from app.bootstrap.logging import configure_logging
from app.bootstrap.settings import Settings, get_settings
from app.interface.http import register_exception_handlers
from app.interface.http.routers import health_router, system_router
from app.ports.readiness import ReadinessService


def create_app(
    settings: Settings | None = None,
    *,
    readiness_service: ReadinessService | None = None,
) -> FastAPI:
    """Create an independently configurable API instance for deployment or tests."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
    )
    application.state.settings = resolved_settings
    application.state.readiness_service = readiness_service

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(system_router)
    return application


app = create_app()
