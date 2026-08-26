"""HTTP router exports."""

from app.interface.http.routers.analysis import router as analysis_router
from app.interface.http.routers.auth import router as auth_router
from app.interface.http.routers.cases import router as cases_router
from app.interface.http.routers.evidence import router as evidence_router
from app.interface.http.routers.health import router as health_router
from app.interface.http.routers.system import router as system_router

__all__ = [
    "analysis_router",
    "auth_router",
    "cases_router",
    "evidence_router",
    "health_router",
    "system_router",
]
