"""Celery worker interface exports."""

from app.interface.workers.celery_app import celery_app

__all__ = ["celery_app"]
