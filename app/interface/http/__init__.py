"""FastAPI interface package."""

from app.interface.http.exception_handlers import register_exception_handlers

__all__ = ["register_exception_handlers"]
