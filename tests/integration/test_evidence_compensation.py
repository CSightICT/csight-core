"""Real PostgreSQL + MinIO compensation tests for Evidence upload failures."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from PIL import Image
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.adapters.file_inspection import PillowImageInspector
from app.adapters.hashing import BoundedSha256Hasher
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.models import (
    CaseEvidenceModel,
    CaseModel,
    CaseSensitivePayloadModel,
    DataLifecycleEventModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.unit_of_work import (
    SQLAlchemyCaseUnitOfWorkFactory,
    create_case_unit_of_work_factory,
)
from app.adapters.storage import MinioObjectStorage
from app.application.evidence import AddImageEvidence
from app.bootstrap.settings import Settings
from app.platform.case import Case, CaseStatus, RequestedAction
from app.platform.errors import EvidenceUploadFailedError, StorageUnavailableError
from app.platform.evidence import EvidenceUploadStatus, build_evidence_object_key
from app.platform.tenant import Principal, Role
from app.ports.observability import CompensationStep
from app.ports.storage import StoredObject

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 26, 8, 9, 10, tzinfo=UTC)


@dataclass(slots=True)
class CompensationContext:
    settings: Settings
    engine: Engine
    factory: SQLAlchemyCaseUnitOfWorkFactory
    storage: MinioObjectStorage
    tenant_id: str
    user_id: str
    object_keys: list[str] = field(default_factory=list)


@pytest.fixture
def compensation_context() -> Generator[CompensationContext, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test Evidence compensation")
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for Evidence compensation integration tests")

    project_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    alembic_command.upgrade(alembic_config, "head")

    engine = get_engine(settings)
    storage = _storage(settings)
    tenant_id, user_id = str(uuid4()), str(uuid4())
    with Session(engine) as session:
        session.add_all(
            [
                TenantModel(
                    id=UUID(tenant_id),
                    slug=f"tenant-{tenant_id}",
                    name="Compensation Test Tenant",
                ),
                UserModel(
                    id=UUID(user_id),
                    tenant_id=UUID(tenant_id),
                    email=f"reviewer-{user_id}@example.test",
                    password_hash="test-password-hash",
                    display_name="Compensation Test Reviewer",
                ),
            ]
        )
        session.commit()

    context = CompensationContext(
        settings=settings,
        engine=engine,
        factory=create_case_unit_of_work_factory(engine),
        storage=storage,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    try:
        yield context
    finally:
        storage_cleanup_errors: list[Exception] = []
        for key in context.object_keys:
            try:
                context.storage.delete(key)
            except Exception as exc:
                storage_cleanup_errors.append(exc)

        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(CaseEvidenceModel).where(
                        CaseEvidenceModel.tenant_id == UUID(context.tenant_id)
                    )
                )
                connection.execute(
                    delete(DataLifecycleEventModel).where(
                        DataLifecycleEventModel.tenant_id == UUID(context.tenant_id)
                    )
                )
                connection.execute(
                    delete(CaseSensitivePayloadModel).where(
                        CaseSensitivePayloadModel.tenant_id == UUID(context.tenant_id)
                    )
                )
                connection.execute(
                    delete(CaseModel).where(CaseModel.tenant_id == UUID(context.tenant_id))
                )
                connection.execute(
                    delete(UserModel).where(UserModel.tenant_id == UUID(context.tenant_id))
                )
                connection.execute(
                    delete(TenantModel).where(TenantModel.id == UUID(context.tenant_id))
                )
        finally:
            clear_engine_cache()

        if storage_cleanup_errors:
            raise RuntimeError(
                "Evidence compensation object cleanup failed for "
                f"{len(storage_cleanup_errors)} object operation(s)"
            ) from storage_cleanup_errors[0]


class StaticClock:
    def now(self) -> datetime:
        return NOW


class FixedIdGenerator:
    def __init__(self, value: str) -> None:
        self._value = value

    def new_id(self) -> str:
        return self._value


class RecordingCompensationObserver:
    def __init__(self) -> None:
        self.events: list[tuple[CompensationStep, str]] = []

    def record_failure(
        self,
        *,
        step: CompensationStep,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        error_type: str,
    ) -> None:
        del tenant_id, case_id, evidence_id
        self.events.append((step, error_type))


class RaiseAfterPutStorage:
    """Inject a partial failure only after the real MinIO write and HEAD check."""

    def __init__(self, delegate: MinioObjectStorage) -> None:
        self._delegate = delegate

    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        length: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        self._delegate.put(
            key=key,
            content=content,
            length=length,
            content_type=content_type,
            sha256=sha256,
        )
        raise RuntimeError("injected storage failure after a verified write")

    def delete(self, key: str) -> None:
        self._delegate.delete(key)

    def exists(self, key: str) -> bool:
        return self._delegate.exists(key)

    def presign_get(self, key: str, *, expires_in: timedelta) -> str:
        return self._delegate.presign_get(key, expires_in=expires_in)

    def is_ready(self) -> bool:
        return self._delegate.is_ready()


def _storage(settings: Settings) -> MinioObjectStorage:
    endpoint = settings.minio_endpoint
    presigned_endpoint = settings.minio_presigned_endpoint_value
    access_key = settings.minio_access_key_value
    secret_key = settings.minio_secret_key_value
    if not endpoint or not presigned_endpoint or not access_key or not secret_key:
        pytest.fail("MinIO settings are required for Evidence compensation integration tests")
    return MinioObjectStorage(
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


def _png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (9, 5), color=(20, 40, 60)).save(stream, format="PNG")
    return stream.getvalue()


def _create_case(context: CompensationContext) -> Case:
    case = Case(
        id=str(uuid4()),
        tenant_id=context.tenant_id,
        status=CaseStatus.RECEIVED,
        order_ref=f"ORD-COMP-{uuid4()}",
        product_ref="SKU-COMPENSATION",
        customer_message="Synthetic compensation integration case",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"source": "integration"},
        created_by=context.user_id,
        created_at=NOW,
        updated_at=NOW,
    )
    with context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()
    return case


def _principal(context: CompensationContext) -> Principal:
    return Principal(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        email=f"reviewer-{context.user_id}@example.test",
        display_name="Compensation Test Reviewer",
        roles=frozenset({Role.REVIEWER}),
    )


def _service(
    context: CompensationContext,
    *,
    evidence_id: str,
    storage: MinioObjectStorage | RaiseAfterPutStorage,
    observer: RecordingCompensationObserver,
) -> AddImageEvidence:
    return AddImageEvidence(
        uow_factory=context.factory,
        storage=storage,
        file_inspector=PillowImageInspector(
            max_bytes=context.settings.max_upload_bytes,
            max_pixels=context.settings.max_image_pixels,
            allowed_mime_types=context.settings.allowed_image_mime_types,
            allowed_extensions=context.settings.allowed_image_extensions,
            hasher=BoundedSha256Hasher(max_bytes=context.settings.max_upload_bytes),
        ),
        storage_bucket=context.settings.minio_bucket,
        clock=StaticClock(),
        id_generator=FixedIdGenerator(evidence_id),
        compensation_observer=observer,
    )


def _assert_failed_row_and_absent_object(
    context: CompensationContext,
    *,
    case: Case,
    evidence_id: str,
    object_key: str,
) -> None:
    assert context.storage.exists(object_key) is False
    with context.factory() as unit_of_work:
        evidence = unit_of_work.evidence.get(
            tenant_id=context.tenant_id,
            case_id=case.id,
            evidence_id=evidence_id,
        )
    assert evidence is not None
    assert evidence.upload_status is EvidenceUploadStatus.FAILED


def test_real_partial_storage_failure_deletes_object_and_marks_database_failed(
    compensation_context: CompensationContext,
) -> None:
    case = _create_case(compensation_context)
    evidence_id = str(uuid4())
    object_key = build_evidence_object_key(
        tenant_id=compensation_context.tenant_id,
        case_id=case.id,
        evidence_id=evidence_id,
    )
    compensation_context.object_keys.append(object_key)
    observer = RecordingCompensationObserver()

    with pytest.raises(StorageUnavailableError):
        _service(
            compensation_context,
            evidence_id=evidence_id,
            storage=RaiseAfterPutStorage(compensation_context.storage),
            observer=observer,
        ).execute(
            principal=_principal(compensation_context),
            case_id=case.id,
            content=BytesIO(_png_bytes()),
            filename="partial-storage-failure.png",
            declared_content_type="image/png",
        )

    _assert_failed_row_and_absent_object(
        compensation_context,
        case=case,
        evidence_id=evidence_id,
        object_key=object_key,
    )
    assert observer.events == []


def test_real_database_finalization_failure_deletes_object_and_commits_failed_status(
    compensation_context: CompensationContext,
) -> None:
    case = _create_case(compensation_context)
    evidence_id = str(uuid4())
    object_key = build_evidence_object_key(
        tenant_id=compensation_context.tenant_id,
        case_id=case.id,
        evidence_id=evidence_id,
    )
    compensation_context.object_keys.append(object_key)
    observer = RecordingCompensationObserver()
    suffix = uuid4().hex[:16]
    function_name = f"test_fail_evidence_available_{suffix}"
    trigger_name = f"test_fail_evidence_available_{suffix}"

    with compensation_context.engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'injected evidence finalization failure';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OF upload_status ON case_evidence
            FOR EACH ROW
            WHEN (
                NEW.case_id = '{case.id}'::uuid
                AND NEW.upload_status = 'AVAILABLE'
            )
            EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        with pytest.raises(EvidenceUploadFailedError):
            _service(
                compensation_context,
                evidence_id=evidence_id,
                storage=compensation_context.storage,
                observer=observer,
            ).execute(
                principal=_principal(compensation_context),
                case_id=case.id,
                content=BytesIO(_png_bytes()),
                filename="database-finalization-failure.png",
                declared_content_type="image/png",
            )

        _assert_failed_row_and_absent_object(
            compensation_context,
            case=case,
            evidence_id=evidence_id,
            object_key=object_key,
        )
        assert observer.events == []
    finally:
        with compensation_context.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger_name} ON case_evidence")
            connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {function_name}()")
