"""Opt-in real PostgreSQL + MinIO + JWT Sprint 1 HTTP vertical slice."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
from dataclasses import dataclass, field
from io import BytesIO
from urllib.request import urlopen
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.models import (
    CaseEvidenceModel,
    CaseModel,
    CaseSensitivePayloadModel,
    CaseStatusHistoryModel,
    DataLifecycleEventModel,
    IdempotencyRecordModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.security import Argon2PasswordHasher
from app.adapters.storage import MinioObjectStorage
from app.bootstrap.settings import Settings
from app.bootstrap.sprint1 import build_sprint1_services
from app.main import create_app
from app.platform.tenant import Role

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

TEST_PASSWORD = "Sprint1-integration-password!"


@dataclass(slots=True)
class E2EContext:
    settings: Settings
    client: TestClient
    tenant_a: UUID
    tenant_b: UUID
    reviewer_id: UUID
    admin_email: str
    reviewer_email: str
    viewer_email: str
    other_reviewer_email: str
    created_role_ids: tuple[UUID, ...]
    object_keys: list[str] = field(default_factory=list)


@pytest.fixture
def e2e_context() -> Generator[E2EContext, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to run the Sprint 1 HTTP E2E")
    settings = Settings()
    if not settings.database_url_value:
        pytest.fail("DATABASE_URL is required for the Sprint 1 HTTP E2E")
    engine = get_engine(settings)
    tenant_a, tenant_b = uuid4(), uuid4()
    admin_id, reviewer_id, viewer_id, other_reviewer_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    admin_email = f"admin-{admin_id}@example.test"
    reviewer_email = f"reviewer-{reviewer_id}@example.test"
    viewer_email = f"viewer-{viewer_id}@example.test"
    other_reviewer_email = f"reviewer-{other_reviewer_id}@example.test"
    password_hash = Argon2PasswordHasher().hash_password(TEST_PASSWORD)

    with Session(engine) as session:
        ensured_roles = {role: _ensure_role(session, role) for role in Role}
        role_ids = {role: result[0] for role, result in ensured_roles.items()}
        created_role_ids = tuple(result[0] for result in ensured_roles.values() if result[1])
        session.add_all(
            [
                TenantModel(id=tenant_a, slug=f"tenant-{tenant_a}", name="E2E Tenant A"),
                TenantModel(id=tenant_b, slug=f"tenant-{tenant_b}", name="E2E Tenant B"),
                UserModel(
                    id=admin_id,
                    tenant_id=tenant_a,
                    email=admin_email,
                    password_hash=password_hash,
                    display_name="E2E Administrator",
                ),
                UserModel(
                    id=reviewer_id,
                    tenant_id=tenant_a,
                    email=reviewer_email,
                    password_hash=password_hash,
                    display_name="E2E Reviewer",
                ),
                UserModel(
                    id=viewer_id,
                    tenant_id=tenant_a,
                    email=viewer_email,
                    password_hash=password_hash,
                    display_name="E2E Viewer",
                ),
                UserModel(
                    id=other_reviewer_id,
                    tenant_id=tenant_b,
                    email=other_reviewer_email,
                    password_hash=password_hash,
                    display_name="Other Tenant Reviewer",
                ),
                UserRoleModel(
                    tenant_id=tenant_a,
                    user_id=admin_id,
                    role_id=role_ids[Role.ADMIN],
                ),
                UserRoleModel(
                    tenant_id=tenant_a,
                    user_id=reviewer_id,
                    role_id=role_ids[Role.REVIEWER],
                ),
                UserRoleModel(
                    tenant_id=tenant_a,
                    user_id=viewer_id,
                    role_id=role_ids[Role.QUALITY_VIEWER],
                ),
                UserRoleModel(
                    tenant_id=tenant_b,
                    user_id=other_reviewer_id,
                    role_id=role_ids[Role.REVIEWER],
                ),
            ]
        )
        session.commit()

    context = E2EContext(
        settings=settings,
        client=TestClient(create_app(settings, sprint1_services=build_sprint1_services(settings))),
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        reviewer_id=reviewer_id,
        admin_email=admin_email,
        reviewer_email=reviewer_email,
        viewer_email=viewer_email,
        other_reviewer_email=other_reviewer_email,
        created_role_ids=created_role_ids,
    )
    try:
        yield context
    finally:
        storage_cleanup_errors: list[Exception] = []
        try:
            storage = _storage(settings)
            for key in context.object_keys:
                try:
                    storage.delete(key)
                except Exception as exc:
                    storage_cleanup_errors.append(exc)
        except Exception as exc:
            storage_cleanup_errors.append(exc)

        tenant_ids = [tenant_a, tenant_b]
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(IdempotencyRecordModel).where(
                        IdempotencyRecordModel.tenant_id.in_(tenant_ids)
                    )
                )
                connection.execute(
                    delete(CaseStatusHistoryModel).where(
                        CaseStatusHistoryModel.tenant_id == tenant_b
                    )
                )
                connection.execute(
                    delete(CaseEvidenceModel).where(CaseEvidenceModel.tenant_id.in_(tenant_ids))
                )
                connection.execute(
                    delete(DataLifecycleEventModel).where(
                        DataLifecycleEventModel.tenant_id == tenant_b
                    )
                )
                connection.execute(
                    delete(CaseSensitivePayloadModel).where(
                        CaseSensitivePayloadModel.tenant_id == tenant_b
                    )
                )
                # Tenant A now has a genuine append-only assignment audit action.
                # Retain it for the disposable integration database instead of
                # weakening the production trigger merely for fixture cleanup.
                connection.execute(delete(CaseModel).where(CaseModel.tenant_id == tenant_b))
                connection.execute(
                    delete(UserRoleModel).where(UserRoleModel.tenant_id.in_(tenant_ids))
                )
                connection.execute(delete(UserModel).where(UserModel.tenant_id == tenant_b))
                connection.execute(delete(TenantModel).where(TenantModel.id == tenant_b))
                connection.execute(
                    update(UserModel).where(UserModel.tenant_id == tenant_a).values(is_active=False)
                )
                connection.execute(
                    update(TenantModel).where(TenantModel.id == tenant_a).values(is_active=False)
                )

            if context.created_role_ids:
                with engine.begin() as connection:
                    connection.execute(
                        delete(RoleModel).where(RoleModel.id.in_(context.created_role_ids))
                    )
        finally:
            clear_engine_cache()

        if storage_cleanup_errors:
            raise RuntimeError(
                f"E2E object cleanup failed for {len(storage_cleanup_errors)} object operation(s)"
            ) from storage_cleanup_errors[0]


def _ensure_role(session: Session, role: Role) -> tuple[UUID, bool]:
    candidate_id = uuid4()
    created_id = session.scalar(
        postgresql_insert(RoleModel)
        .values(id=candidate_id, name=role.value)
        .on_conflict_do_nothing(index_elements=[RoleModel.name])
        .returning(RoleModel.id)
    )
    if created_id is not None:
        return created_id, True
    role_id = session.scalar(select(RoleModel.id).where(RoleModel.name == role.value))
    assert role_id is not None
    return role_id, False


def _storage(settings: Settings) -> MinioObjectStorage:
    endpoint = settings.minio_endpoint
    presigned_endpoint = settings.minio_presigned_endpoint_value
    access_key = settings.minio_access_key_value
    secret_key = settings.minio_secret_key_value
    assert endpoint and presigned_endpoint and access_key and secret_key
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
    Image.new("RGB", (12, 7), color=(12, 34, 56)).save(stream, format="PNG")
    return stream.getvalue()


def _login(client: TestClient, *, tenant_slug: str, email: str) -> str:
    response = client.post(
        "/api/v1/auth/token",
        json={"tenant_slug": tenant_slug, "email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_real_login_case_evidence_signed_download_and_tenant_isolation(
    e2e_context: E2EContext,
) -> None:
    tenant_a_slug = f"tenant-{e2e_context.tenant_a}"
    admin_token = _login(
        e2e_context.client,
        tenant_slug=tenant_a_slug,
        email=e2e_context.admin_email,
    )
    reviewer_token = _login(
        e2e_context.client,
        tenant_slug=tenant_a_slug,
        email=e2e_context.reviewer_email,
    )
    viewer_token = _login(
        e2e_context.client,
        tenant_slug=tenant_a_slug,
        email=e2e_context.viewer_email,
    )
    other_token = _login(
        e2e_context.client,
        tenant_slug=f"tenant-{e2e_context.tenant_b}",
        email=e2e_context.other_reviewer_email,
    )
    request_body = {
        "order_ref": f"ORD-E2E-{uuid4()}",
        "product_ref": "SKU-E2E",
        "customer_message": "The product arrived visibly damaged.",
        "requested_action": "EXCHANGE",
        "attributes": {"channel": "integration"},
    }
    idempotency_key = f"e2e-{uuid4()}"

    created = e2e_context.client.post(
        "/api/v1/cases",
        headers={**_auth(reviewer_token), "Idempotency-Key": idempotency_key},
        json=request_body,
    )
    assert created.status_code == 201
    case_id = UUID(created.json()["case_id"])
    replay = e2e_context.client.post(
        "/api/v1/cases",
        headers={**_auth(reviewer_token), "Idempotency-Key": idempotency_key},
        json=request_body,
    )
    assert replay.status_code == 200
    assert replay.json()["case_id"] == str(case_id)
    conflicting_body = {**request_body, "customer_message": "Different body"}
    conflict = e2e_context.client.post(
        "/api/v1/cases",
        headers={**_auth(reviewer_token), "Idempotency-Key": idempotency_key},
        json=conflicting_body,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    viewer_create = e2e_context.client.post(
        "/api/v1/cases",
        headers=_auth(viewer_token),
        json=request_body,
    )
    assert viewer_create.status_code == 403

    unassigned_detail = e2e_context.client.get(
        f"/api/v1/cases/{case_id}",
        headers=_auth(reviewer_token),
    )
    assert unassigned_detail.status_code == 404
    assigned = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/assignment",
        headers=_auth(admin_token),
        json={
            "assignee_id": str(e2e_context.reviewer_id),
            "expected_version": 0,
            "rationale": "Assign the integration Case to its authenticated reviewer.",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["current_assignee_id"] == str(e2e_context.reviewer_id)

    payload = _png_bytes()
    uploaded = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence",
        headers=_auth(reviewer_token),
        data={"evidence_type": "IMAGE"},
        files={"file": ("../../customer-photo.png", payload, "image/png")},
    )
    assert uploaded.status_code == 201
    evidence = uploaded.json()
    evidence_id = UUID(evidence["evidence_id"])
    object_key = f"tenants/{e2e_context.tenant_a}/cases/{case_id}/evidence/{evidence_id}/original"
    e2e_context.object_keys.append(object_key)
    assert evidence["upload_status"] == "AVAILABLE"
    assert evidence["original_filename"] == "customer-photo.png"
    assert evidence["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (evidence["width"], evidence["height"]) == (12, 7)

    invalid = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence",
        headers=_auth(reviewer_token),
        data={"evidence_type": "IMAGE"},
        files={"file": ("not-image.png", b"not an image", "image/png")},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_IMAGE_CONTENT"
    viewer_upload = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence",
        headers=_auth(viewer_token),
        data={"evidence_type": "IMAGE"},
        files={"file": ("image.png", payload, "image/png")},
    )
    assert viewer_upload.status_code == 403

    listed = e2e_context.client.get(
        "/api/v1/cases",
        headers=_auth(viewer_token),
        params={"order_ref": str(request_body["order_ref"])},
    )
    detail = e2e_context.client.get(f"/api/v1/cases/{case_id}", headers=_auth(reviewer_token))
    history = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/status-history",
        headers=_auth(reviewer_token),
    )
    metadata = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}",
        headers=_auth(reviewer_token),
    )
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert "customer_message" not in listed.text
    assert detail.status_code == 200
    assert detail.json()["latest_analysis_run"] is None
    assert detail.json()["evidence"][0]["evidence_id"] == str(evidence_id)
    assert history.status_code == 200
    assert history.json()["items"][0]["to_status"] == "RECEIVED"
    assert metadata.status_code == 200

    hidden_case = e2e_context.client.get(f"/api/v1/cases/{case_id}", headers=_auth(other_token))
    hidden_evidence = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}",
        headers=_auth(other_token),
    )
    hidden_access = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url",
        headers=_auth(other_token),
    )
    hidden_content = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/content",
        headers=_auth(other_token),
    )
    assert hidden_case.status_code == 404
    assert hidden_case.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert hidden_evidence.status_code == 404
    assert hidden_evidence.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert hidden_access.status_code == 404
    assert hidden_access.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert hidden_content.status_code == 404
    assert hidden_content.json()["error"]["code"] == "CASE_NOT_FOUND"

    other_case = e2e_context.client.post(
        "/api/v1/cases",
        headers=_auth(other_token),
        json={
            "order_ref": "ORD-TENANT-B",
            "product_ref": "SKU-TENANT-B",
            "customer_message": "Cross-tenant role-ordering probe.",
            "requested_action": "INFORMATION",
        },
    )
    assert other_case.status_code == 201
    hidden_upload = e2e_context.client.post(
        f"/api/v1/cases/{other_case.json()['case_id']}/evidence",
        headers=_auth(viewer_token),
        data={"evidence_type": "IMAGE"},
        files={"file": ("hidden.png", payload, "image/png")},
    )
    assert hidden_upload.status_code == 404
    assert hidden_upload.json()["error"]["code"] == "CASE_NOT_FOUND"

    access = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url",
        headers=_auth(reviewer_token),
    )
    assert access.status_code == 200
    with urlopen(access.json()["url"], timeout=5) as response:
        assert response.read() == payload
    content = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/content",
        headers=_auth(reviewer_token),
    )
    assert content.status_code == 200
    assert content.content == payload
    assert content.headers["content-type"] == "image/png"
    assert content.headers["cache-control"] == "private, no-store"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["etag"] == f'"{hashlib.sha256(payload).hexdigest()}"'

    storage = _storage(e2e_context.settings)
    assert storage.exists(object_key) is True
    with Session(get_engine(e2e_context.settings)) as session:
        stored = session.scalar(
            select(CaseEvidenceModel).where(
                CaseEvidenceModel.tenant_id == e2e_context.tenant_a,
                CaseEvidenceModel.case_id == case_id,
                CaseEvidenceModel.id == evidence_id,
            )
        )
        assert stored is not None
        assert stored.object_key == object_key
        assert stored.storage_bucket == e2e_context.settings.minio_bucket
        assert stored.upload_status == "AVAILABLE"

    storage.delete(object_key)
    e2e_context.object_keys.remove(object_key)
    missing_object_access = e2e_context.client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url",
        headers=_auth(reviewer_token),
    )
    assert missing_object_access.status_code == 500
    assert missing_object_access.json()["error"]["code"] == "EVIDENCE_UPLOAD_FAILED"
    missing_object_content = e2e_context.client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/content",
        headers=_auth(reviewer_token),
    )
    assert missing_object_content.status_code == 500
    assert missing_object_content.json()["error"]["code"] == "EVIDENCE_UPLOAD_FAILED"
