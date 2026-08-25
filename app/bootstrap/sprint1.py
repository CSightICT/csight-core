"""Composition root for the Sprint 1 authenticated Case/Evidence vertical slice."""

from datetime import timedelta

from app.adapters.file_inspection import PillowImageInspector
from app.adapters.hashing import BoundedSha256Hasher
from app.adapters.observability import StructuredCompensationFailureObserver
from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepositoryFactoryAdapter
from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.unit_of_work import create_case_unit_of_work_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.security import Argon2PasswordHasher, PyJWTAccessTokenCodec
from app.adapters.storage import MinioObjectStorage
from app.application.auth import AuthenticateUser, ResolvePrincipal
from app.application.cases import (
    CreateCase,
    GetCase,
    GetCaseStatusHistory,
    ListCases,
)
from app.application.evidence import (
    AddImageEvidence,
    CreateEvidenceAccessUrl,
    GetEvidenceMetadata,
    ListCaseEvidence,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer


class Sprint1ConfigurationError(RuntimeError):
    """Raised without secret values when mandatory Sprint 1 settings are absent."""


def sprint1_is_configured(settings: Settings) -> bool:
    """Return whether all infrastructure/security values needed by the API exist."""

    return all(
        (
            settings.database_url_value,
            settings.jwt_secret_key_value,
            settings.minio_endpoint,
            settings.minio_presigned_endpoint_value,
            settings.minio_access_key_value,
            settings.minio_secret_key_value,
        )
    )


def build_sprint1_services(settings: Settings) -> Sprint1ServiceContainer:
    """Build reusable, thread-safe services; repository UoWs open sessions per call."""

    missing = _missing_configuration(settings)
    if missing:
        names = ", ".join(missing)
        raise Sprint1ConfigurationError(f"Sprint 1 configuration is incomplete: {names}")

    jwt_secret_key = _required(settings.jwt_secret_key_value, "JWT_SECRET_KEY")
    minio_endpoint = _required(settings.minio_endpoint, "MINIO_ENDPOINT")
    presigned_endpoint = _required(
        settings.minio_presigned_endpoint_value,
        "MINIO_PRESIGNED_ENDPOINT",
    )
    minio_access_key = _required(settings.minio_access_key_value, "MINIO_ACCESS_KEY")
    minio_secret_key = _required(settings.minio_secret_key_value, "MINIO_SECRET_KEY")

    engine = get_engine(settings)
    session_factory = create_session_factory(engine)
    identities = SQLAlchemyIdentityRepositoryFactoryAdapter(session_factory)
    uow_factory = create_case_unit_of_work_factory(engine)
    clock = UtcClock()
    id_generator = Uuid4Generator()
    token_ttl = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    token_codec = PyJWTAccessTokenCodec(
        secret_key=jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_token_ttl=token_ttl,
    )
    storage = MinioObjectStorage(
        endpoint=minio_endpoint,
        presigned_endpoint=presigned_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        bucket=settings.minio_bucket,
        region=settings.minio_region,
        secure=settings.minio_secure,
        presigned_secure=settings.minio_presigned_secure_value,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    inspector = PillowImageInspector(
        max_bytes=settings.max_upload_bytes,
        max_pixels=settings.max_image_pixels,
        allowed_mime_types=settings.allowed_image_mime_types,
        allowed_extensions=settings.allowed_image_extensions,
        hasher=BoundedSha256Hasher(max_bytes=settings.max_upload_bytes),
    )
    get_evidence = GetEvidenceMetadata(uow_factory=uow_factory)

    return Sprint1ServiceContainer(
        authenticate_user=AuthenticateUser(
            identities=identities,
            password_hasher=Argon2PasswordHasher(),
            token_codec=token_codec,
            token_ttl=token_ttl,
        ),
        resolve_principal=ResolvePrincipal(
            identities=identities,
            token_codec=token_codec,
        ),
        create_case=CreateCase(
            uow_factory=uow_factory,
            clock=clock,
            id_generator=id_generator,
        ),
        list_cases=ListCases(uow_factory=uow_factory),
        get_case=GetCase(uow_factory=uow_factory),
        get_case_status_history=GetCaseStatusHistory(uow_factory=uow_factory),
        add_image_evidence=AddImageEvidence(
            uow_factory=uow_factory,
            storage=storage,
            file_inspector=inspector,
            storage_bucket=settings.minio_bucket,
            clock=clock,
            id_generator=id_generator,
            compensation_observer=StructuredCompensationFailureObserver(),
        ),
        list_case_evidence=ListCaseEvidence(uow_factory=uow_factory),
        get_evidence_metadata=get_evidence,
        create_evidence_access_url=CreateEvidenceAccessUrl(
            get_evidence=get_evidence,
            storage=storage,
            clock=clock,
            ttl=timedelta(seconds=settings.signed_url_ttl_seconds),
        ),
    )


def _missing_configuration(settings: Settings) -> tuple[str, ...]:
    candidates = (
        ("DATABASE_URL", settings.database_url_value),
        ("JWT_SECRET_KEY", settings.jwt_secret_key_value),
        ("MINIO_ENDPOINT", settings.minio_endpoint),
        ("MINIO_PRESIGNED_ENDPOINT", settings.minio_presigned_endpoint_value),
        ("MINIO_ACCESS_KEY", settings.minio_access_key_value),
        ("MINIO_SECRET_KEY", settings.minio_secret_key_value),
    )
    return tuple(name for name, value in candidates if not value)


def _required(value: str | None, name: str) -> str:
    if not value:
        raise Sprint1ConfigurationError(f"{name} is required")
    return value
