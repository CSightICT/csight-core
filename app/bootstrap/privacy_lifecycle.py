"""Composition root for explicit privacy lifecycle operator jobs."""

from __future__ import annotations

from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.privacy_lifecycle import (
    create_privacy_lifecycle_unit_of_work_factory,
)
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.storage import MinioObjectStorage
from app.application.privacy_lifecycle import (
    PrivacyLifecycleServices,
    PurgeExpiredSensitivePayloads,
    ReconcileEvidenceConsistency,
)
from app.bootstrap.settings import Settings


class PrivacyLifecycleConfigurationError(RuntimeError):
    """Raised without exposing configuration values or credentials."""


def build_privacy_lifecycle_services(
    settings: Settings,
    *,
    evidence_stale_after: timedelta = timedelta(hours=1),
) -> PrivacyLifecycleServices:
    purge_sensitive_payloads = build_sensitive_payload_retention_service(settings)
    endpoint = _required(settings.minio_endpoint, "MINIO_ENDPOINT")
    presigned_endpoint = _required(
        settings.minio_presigned_endpoint_value,
        "MINIO_PRESIGNED_ENDPOINT",
    )
    access_key = _required(settings.minio_access_key_value, "MINIO_ACCESS_KEY")
    secret_key = _required(settings.minio_secret_key_value, "MINIO_SECRET_KEY")
    engine = get_engine(settings)
    uow_factory = create_privacy_lifecycle_unit_of_work_factory(engine)
    storage = MinioObjectStorage(
        endpoint=endpoint,
        presigned_endpoint=presigned_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=settings.minio_bucket,
        region=settings.minio_region,
        secure=settings.minio_secure,
        presigned_secure=settings.minio_presigned_secure_value,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    clock = UtcClock()
    id_generator = Uuid4Generator()
    return PrivacyLifecycleServices(
        purge_sensitive_payloads=purge_sensitive_payloads,
        reconcile_evidence=ReconcileEvidenceConsistency(
            uow_factory=uow_factory,
            inventory=storage,
            versioned_storage=storage,
            clock=clock,
            id_generator=id_generator,
            stale_after=evidence_stale_after,
        ),
    )


def build_sensitive_payload_retention_service(
    settings: Settings,
) -> PurgeExpiredSensitivePayloads:
    """Build the DB-only retention service without granting object deletion capability."""

    database_url = _required(settings.database_url_value, "DATABASE_URL")
    del database_url  # get_engine consumes the already validated Settings value.
    _required(
        settings.sensitive_payload_retention_policy_version_value,
        "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION",
    )
    if settings.sensitive_payload_retention_days_value is None:
        raise PrivacyLifecycleConfigurationError("SENSITIVE_PAYLOAD_RETENTION_DAYS is required")
    return PurgeExpiredSensitivePayloads(
        uow_factory=create_privacy_lifecycle_unit_of_work_factory(get_engine(settings)),
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
    )


def _required(value: str | None, name: str) -> str:
    if not value:
        raise PrivacyLifecycleConfigurationError(f"{name} is required")
    return value


__all__ = [
    "PrivacyLifecycleConfigurationError",
    "build_privacy_lifecycle_services",
    "build_sensitive_payload_retention_service",
]
