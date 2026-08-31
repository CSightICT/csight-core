"""HTTP-level tests for the Sprint 1 authentication, Case, and Evidence contract."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest
from fastapi.testclient import TestClient

from app.application.auth import LoginCommand, LoginResult
from app.application.cases import (
    CasePage,
    CreateCaseCommand,
    CreateCaseResult,
    ListCasesQuery,
)
from app.application.evidence import EvidenceAccessUrl, EvidenceContent
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer
from app.main import create_app
from app.platform.case import (
    Case,
    CaseStatus,
    CaseStatusTransition,
    RequestedAction,
)
from app.platform.errors import (
    AuthenticationRequiredError,
    CaseNotFoundError,
    FileTooLargeError,
    IdempotencyKeyReusedError,
    InvalidCredentialsError,
)
from app.platform.evidence import EvidenceMetadata, EvidenceType, EvidenceUploadStatus
from app.platform.tenant import Permission, Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)


def _principal(role: Role = Role.REVIEWER) -> Principal:
    return Principal(
        user_id=f"user-{role.value.lower()}",
        tenant_id="tenant-a",
        email=f"{role.value.lower()}@example.test",
        display_name=role.value.title(),
        roles=frozenset({role}),
    )


def _case() -> Case:
    return Case(
        id="case-1",
        tenant_id="tenant-a",
        status=CaseStatus.RECEIVED,
        order_ref="ORD-1",
        product_ref="SKU-1",
        customer_message="Sensitive customer message",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"days_since_purchase": 3},
        created_by="user-reviewer",
        created_at=NOW,
        updated_at=NOW,
    )


def _history() -> CaseStatusTransition:
    return CaseStatusTransition(
        id="history-1",
        tenant_id="tenant-a",
        case_id="case-1",
        from_status=None,
        to_status=CaseStatus.RECEIVED,
        actor_id="user-reviewer",
        reason="case_created",
        occurred_at=NOW,
    )


def _evidence() -> EvidenceMetadata:
    return EvidenceMetadata(
        id="evidence-1",
        tenant_id="tenant-a",
        case_id="case-1",
        evidence_type=EvidenceType.IMAGE,
        upload_status=EvidenceUploadStatus.AVAILABLE,
        storage_bucket="private-bucket",
        object_key="tenants/tenant-a/cases/case-1/evidence/evidence-1/original",
        original_filename="image.png",
        content_type="image/png",
        size_bytes=8,
        sha256="a" * 64,
        width=1,
        height=1,
        created_by="user-reviewer",
        created_at=NOW,
        updated_at=NOW,
    )


@dataclass(slots=True)
class FakeAuthenticateUser:
    command: LoginCommand | None = None

    def execute(self, command: LoginCommand) -> LoginResult:
        self.command = command
        if command.password.get_secret_value() != "correct-password":
            raise InvalidCredentialsError()
        return LoginResult(access_token="valid-token", expires_in=1800)


class FakeResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token == "valid-token":
            return _principal()
        if token == "viewer-token":
            return _principal(Role.QUALITY_VIEWER)
        raise AuthenticationRequiredError()


@dataclass(slots=True)
class FakeCreateCase:
    commands: list[CreateCaseCommand] = field(default_factory=list)
    principals: list[Principal] = field(default_factory=list)

    def execute(
        self,
        *,
        principal: Principal,
        command: CreateCaseCommand,
    ) -> CreateCaseResult:
        principal.require(Permission.CASE_CREATE)
        self.principals.append(principal)
        self.commands.append(command)
        if command.idempotency_key == "conflict-key":
            raise IdempotencyKeyReusedError()
        return CreateCaseResult(case=_case(), replayed=command.idempotency_key == "replay-key")


@dataclass(slots=True)
class FakeListCases:
    queries: list[ListCasesQuery] = field(default_factory=list)

    def execute(self, *, principal: Principal, query: ListCasesQuery) -> CasePage:
        principal.require(Permission.CASE_READ)
        self.queries.append(query)
        return CasePage(items=(_case(),), page=query.page, page_size=query.page_size, total=1)


class FakeGetCase:
    def execute(self, *, principal: Principal, case_id: str) -> Case:
        principal.require(Permission.CASE_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        if case_id == "corrupt-case":
            return Case.model_validate({})
        return _case()


class FakeGetCaseStatusHistory:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[CaseStatusTransition, ...]:
        principal.require(Permission.CASE_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        return (_history(),)


@dataclass(slots=True)
class FakeAddImageEvidence:
    filename: str | None = None
    declared_content_type: str | None = None
    evidence_type: EvidenceType | None = None
    content: bytes = b""
    idempotency_key: str | None = None

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
        evidence_type: EvidenceType = EvidenceType.IMAGE,
        idempotency_key: str | None = None,
    ) -> EvidenceMetadata:
        principal.require(Permission.EVIDENCE_UPLOAD)
        if filename == "too-large.png":
            raise FileTooLargeError()
        self.filename = filename
        self.declared_content_type = declared_content_type
        self.evidence_type = evidence_type
        self.idempotency_key = idempotency_key
        self.content = content.read()
        return _evidence()


class FakeListCaseEvidence:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[EvidenceMetadata, ...]:
        principal.require(Permission.CASE_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        return (_evidence(),)


class FakeGetEvidenceMetadata:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceMetadata:
        principal.require(Permission.CASE_READ)
        if case_id == "missing-case":
            raise CaseNotFoundError()
        return _evidence()


class FakeCreateEvidenceAccessUrl:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceAccessUrl:
        principal.require(Permission.CASE_READ)
        return EvidenceAccessUrl(
            evidence_id=evidence_id,
            url="http://127.0.0.1:9000/private/signed-value",
            expires_at=NOW + timedelta(minutes=15),
        )


class FakeReadEvidenceContent:
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceContent:
        principal.require(Permission.CASE_READ)
        return EvidenceContent(
            evidence_id=evidence_id,
            content=b"png-data",
            content_type="image/png",
            sha256="a" * 64,
        )


@dataclass(slots=True)
class HTTPTestContext:
    client: TestClient
    authenticate: FakeAuthenticateUser
    create_case: FakeCreateCase
    list_cases: FakeListCases
    add_evidence: FakeAddImageEvidence


def _build_http_context(
    *,
    max_upload_bytes: int = 10 * 1024 * 1024,
    raise_server_exceptions: bool = True,
) -> HTTPTestContext:
    authenticate = FakeAuthenticateUser()
    create_case = FakeCreateCase()
    list_cases = FakeListCases()
    add_evidence = FakeAddImageEvidence()
    services = Sprint1ServiceContainer(
        authenticate_user=authenticate,
        resolve_principal=FakeResolvePrincipal(),
        create_case=create_case,
        list_cases=list_cases,
        get_case=FakeGetCase(),
        get_case_status_history=FakeGetCaseStatusHistory(),
        add_image_evidence=add_evidence,
        list_case_evidence=FakeListCaseEvidence(),
        get_evidence_metadata=FakeGetEvidenceMetadata(),
        create_evidence_access_url=FakeCreateEvidenceAccessUrl(),
        read_evidence_content=FakeReadEvidenceContent(),
        get_case_assignment=FakeGetCase(),  # pyright: ignore[reportArgumentType]
        assign_case=FakeGetCase(),  # pyright: ignore[reportArgumentType]
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        max_upload_bytes=max_upload_bytes,
    )
    return HTTPTestContext(
        client=TestClient(
            create_app(settings, sprint1_services=services),
            raise_server_exceptions=raise_server_exceptions,
        ),
        authenticate=authenticate,
        create_case=create_case,
        list_cases=list_cases,
        add_evidence=add_evidence,
    )


@pytest.fixture
def http_context() -> HTTPTestContext:
    return _build_http_context()


def _authorization(token: str = "valid-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _case_request() -> dict[str, object]:
    return {
        "order_ref": "ORD-1",
        "product_ref": "SKU-1",
        "customer_message": "Package is damaged.",
        "requested_action": "EXCHANGE",
        "attributes": {"days_since_purchase": 3},
    }


def test_login_and_me_contract(http_context: HTTPTestContext) -> None:
    login = http_context.client.post(
        "/api/v1/auth/token",
        json={
            "tenant_slug": " Tenant-A ",
            "email": " Reviewer@Example.Test ",
            "password": "correct-password",
        },
    )

    assert login.status_code == 200
    assert login.json() == {
        "access_token": "valid-token",
        "token_type": "bearer",
        "expires_in": 1800,
    }
    assert login.headers["Cache-Control"] == "no-store"
    assert login.headers["Pragma"] == "no-cache"
    assert http_context.authenticate.command is not None
    assert http_context.authenticate.command.tenant_slug == "tenant-a"
    assert http_context.authenticate.command.email == "reviewer@example.test"

    me = http_context.client.get("/api/v1/auth/me", headers=_authorization())
    assert me.status_code == 200
    assert me.json() == {
        "user_id": "user-reviewer",
        "tenant_id": "tenant-a",
        "email": "reviewer@example.test",
        "display_name": "Reviewer",
        "roles": ["REVIEWER"],
    }


def test_invalid_login_and_missing_or_invalid_bearer_return_401(
    http_context: HTTPTestContext,
) -> None:
    invalid_login = http_context.client.post(
        "/api/v1/auth/token",
        json={
            "tenant_slug": "tenant-a",
            "email": "reviewer@example.test",
            "password": "wrong-password",
        },
    )
    missing = http_context.client.get("/api/v1/auth/me")
    invalid = http_context.client.get(
        "/api/v1/auth/me",
        headers=_authorization("invalid-token"),
    )

    for response, code in (
        (invalid_login, "INVALID_CREDENTIALS"),
        (missing, "AUTHENTICATION_REQUIRED"),
        (invalid, "AUTHENTICATION_REQUIRED"),
    ):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["correlation_id"]


def test_case_create_uses_principal_tenant_and_idempotency_status(
    http_context: HTTPTestContext,
) -> None:
    created = http_context.client.post(
        "/api/v1/cases",
        headers={**_authorization(), "Idempotency-Key": "new-key"},
        json=_case_request(),
    )
    replayed = http_context.client.post(
        "/api/v1/cases",
        headers={**_authorization(), "Idempotency-Key": "replay-key"},
        json=_case_request(),
    )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert created.json() == {
        "case_id": "case-1",
        "status": "RECEIVED",
        "created_at": "2026-08-26T01:02:03Z",
    }
    assert [command.idempotency_key for command in http_context.create_case.commands] == [
        "new-key",
        "replay-key",
    ]
    assert all(
        principal.tenant_id == "tenant-a" for principal in http_context.create_case.principals
    )


def test_case_input_rejects_tenant_id_and_idempotency_conflict_is_409(
    http_context: HTTPTestContext,
) -> None:
    body = _case_request()
    body["tenant_id"] = "tenant-b"
    rejected = http_context.client.post(
        "/api/v1/cases",
        headers=_authorization(),
        json=body,
    )
    conflict = http_context.client.post(
        "/api/v1/cases",
        headers={**_authorization(), "Idempotency-Key": "conflict-key"},
        json=_case_request(),
    )

    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(http_context.create_case.commands) == 1
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_case_list_filters_and_excludes_customer_message(
    http_context: HTTPTestContext,
) -> None:
    response = http_context.client.get(
        "/api/v1/cases",
        headers=_authorization(),
        params={
            "status": "RECEIVED",
            "order_ref": "ORD-1",
            "product_ref": "SKU-1",
            "created_from": "2026-08-01T00:00:00Z",
            "created_to": "2026-08-31T00:00:00Z",
            "page": 2,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["page"] == 2
    assert response.json()["page_size"] == 10
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["case_id"] == "case-1"
    assert "customer_message" not in response.text
    query = http_context.list_cases.queries[-1]
    assert query.status is CaseStatus.RECEIVED
    assert query.created_from == datetime(2026, 8, 1, tzinfo=UTC)

    tenant_injection = http_context.client.get(
        "/api/v1/cases",
        headers=_authorization(),
        params={"tenant_id": "tenant-b"},
    )
    assert tenant_injection.status_code == 422
    assert tenant_injection.json()["error"]["code"] == "VALIDATION_ERROR"


def test_case_detail_and_status_history_include_sprint1_views(
    http_context: HTTPTestContext,
) -> None:
    detail = http_context.client.get("/api/v1/cases/case-1", headers=_authorization())
    history = http_context.client.get(
        "/api/v1/cases/case-1/status-history",
        headers=_authorization(),
    )

    assert detail.status_code == 200
    assert detail.json()["customer_message"] == "Sensitive customer message"
    assert detail.json()["latest_analysis_run"] is None
    assert detail.json()["evidence"][0]["evidence_id"] == "evidence-1"
    assert detail.json()["status_history"][0]["to_status"] == "RECEIVED"
    assert "storage_bucket" not in detail.text
    assert "object_key" not in detail.text

    assert history.status_code == 200
    assert history.json()["items"][0]["reason"] == "case_created"


def test_other_or_missing_tenant_scoped_case_is_hidden_as_404(
    http_context: HTTPTestContext,
) -> None:
    response = http_context.client.get(
        "/api/v1/cases/missing-case",
        headers=_authorization(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_evidence_upload_list_metadata_and_access_url(
    http_context: HTTPTestContext,
) -> None:
    uploaded = http_context.client.post(
        "/api/v1/cases/case-1/evidence",
        headers={**_authorization(), "Idempotency-Key": "evidence-upload-1"},
        data={"evidence_type": "IMAGE"},
        files={"file": ("image.png", b"png-data", "image/png")},
    )
    listed = http_context.client.get(
        "/api/v1/cases/case-1/evidence",
        headers=_authorization(),
    )
    metadata = http_context.client.get(
        "/api/v1/cases/case-1/evidence/evidence-1",
        headers=_authorization(),
    )
    access = http_context.client.post(
        "/api/v1/cases/case-1/evidence/evidence-1/access-url",
        headers=_authorization(),
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["upload_status"] == "AVAILABLE"
    assert http_context.add_evidence.filename == "image.png"
    assert http_context.add_evidence.declared_content_type == "image/png"
    assert http_context.add_evidence.evidence_type is EvidenceType.IMAGE
    assert http_context.add_evidence.idempotency_key == "evidence-upload-1"
    assert http_context.add_evidence.content == b"png-data"

    assert listed.status_code == 200
    assert listed.json()["items"][0]["evidence_id"] == "evidence-1"
    assert metadata.status_code == 200
    assert metadata.json()["sha256"] == "a" * 64
    assert access.status_code == 200
    assert access.headers["Cache-Control"] == "no-store"
    assert access.json() == {
        "evidence_id": "evidence-1",
        "url": "http://127.0.0.1:9000/private/signed-value",
        "expires_at": "2026-08-26T01:17:03Z",
    }

    content = http_context.client.get(
        "/api/v1/cases/case-1/evidence/evidence-1/content",
        headers=_authorization(),
    )
    assert content.status_code == 200
    assert content.content == b"png-data"
    assert content.headers["Content-Type"] == "image/png"
    assert content.headers["Cache-Control"] == "private, no-store"
    assert content.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert content.headers["ETag"] == f'"{"a" * 64}"'
    assert content.headers["X-Content-Type-Options"] == "nosniff"


def test_evidence_role_and_file_errors_use_standard_codes(
    http_context: HTTPTestContext,
) -> None:
    forbidden = http_context.client.post(
        "/api/v1/cases/case-1/evidence",
        headers=_authorization("viewer-token"),
        data={"evidence_type": "IMAGE"},
        files={"file": ("image.png", b"png-data", "image/png")},
    )
    too_large = http_context.client.post(
        "/api/v1/cases/case-1/evidence",
        headers=_authorization(),
        data={"evidence_type": "IMAGE"},
        files={"file": ("too-large.png", b"png-data", "image/png")},
    )
    unauthenticated_content = http_context.client.get(
        "/api/v1/cases/case-1/evidence/evidence-1/content"
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert unauthenticated_content.status_code == 401
    assert unauthenticated_content.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_evidence_request_body_is_bounded_before_multipart_spooling() -> None:
    context = _build_http_context(max_upload_bytes=16)
    oversized_body = b"x" * (1024 * 1024 + 17)

    response = context.client.post(
        "/api/v1/cases/case-1/evidence",
        headers={
            **_authorization(),
            "Content-Type": "multipart/form-data; boundary=csight-test",
            "X-Correlation-ID": "corr-upload-limit",
        },
        content=oversized_body,
    )

    assert response.status_code == 413, response.text
    assert response.headers["X-Correlation-ID"] == "corr-upload-limit"
    assert response.json()["error"] == {
        "code": "FILE_TOO_LARGE",
        "message": "The uploaded file exceeds the configured size limit.",
        "details": {},
        "correlation_id": "corr-upload-limit",
    }
    assert context.add_evidence.filename is None


def test_chunked_evidence_request_is_bounded_without_content_length() -> None:
    context = _build_http_context(max_upload_bytes=16)

    def chunks() -> Iterator[bytes]:
        yield (
            b"--csight-test\r\n"
            b'Content-Disposition: form-data; name="evidence_type"\r\n\r\n'
            b"IMAGE\r\n"
            b"--csight-test\r\n"
            b'Content-Disposition: form-data; name="file"; filename="large.png"\r\n'
            b"Content-Type: image/png\r\n\r\n"
        )
        yield b"x" * 600_000
        yield b"y" * 600_000
        yield b"\r\n--csight-test--\r\n"

    response = context.client.post(
        "/api/v1/cases/case-1/evidence",
        headers={
            **_authorization(),
            "Content-Type": "multipart/form-data; boundary=csight-test",
        },
        content=chunks(),
    )

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert context.add_evidence.filename is None


def test_validation_envelope_never_echoes_password(http_context: HTTPTestContext) -> None:
    response = http_context.client.post(
        "/api/v1/auth/token",
        json={
            "tenant_slug": "tenant-a",
            "email": "reviewer@example.test",
            "password": "",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["correlation_id"]
    assert '"password":""' not in response.text


def test_correlation_id_is_preserved_or_safely_generated(
    http_context: HTTPTestContext,
) -> None:
    preserved = http_context.client.get(
        "/missing",
        headers={"X-Correlation-ID": "corr-http-test"},
    )
    generated = http_context.client.get(
        "/missing",
        headers={"X-Correlation-ID": "unsafe correlation value"},
    )

    assert preserved.headers["X-Correlation-ID"] == "corr-http-test"
    assert preserved.json()["error"]["correlation_id"] == "corr-http-test"
    generated_id = generated.headers["X-Correlation-ID"]
    assert generated_id != "unsafe correlation value"
    assert generated.json()["error"]["correlation_id"] == generated_id
    assert len(generated_id) <= 128


def test_internal_model_validation_failure_is_not_reported_as_client_422() -> None:
    context = _build_http_context(raise_server_exceptions=False)

    response = context.client.get(
        "/api/v1/cases/corrupt-case",
        headers=_authorization(),
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def _request_property_names(
    *,
    schema: dict[str, object],
    document: dict[str, object],
) -> set[str]:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        current: object = document
        for component in reference.removeprefix("#/").split("/"):
            assert isinstance(current, dict)
            current = current[component]
        assert isinstance(current, dict)
        return _request_property_names(schema=current, document=document)
    names: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        names.update(str(name) for name in properties)
        for nested in properties.values():
            if isinstance(nested, dict):
                names.update(_request_property_names(schema=nested, document=document))
    for keyword in ("allOf", "anyOf", "oneOf"):
        nested_schemas = schema.get(keyword)
        if isinstance(nested_schemas, list):
            for nested in nested_schemas:
                if isinstance(nested, dict):
                    names.update(_request_property_names(schema=nested, document=document))
    return names


def test_openapi_matches_tenant_free_inputs_and_bearer_contract(
    http_context: HTTPTestContext,
) -> None:
    document = http_context.client.get("/openapi.json").json()
    paths = document["paths"]

    for path, method in (
        ("/api/v1/auth/token", "post"),
        ("/api/v1/cases", "post"),
        ("/api/v1/cases/{case_id}/evidence", "post"),
    ):
        operation = paths[path][method]
        content = operation["requestBody"]["content"]
        media_schema = next(iter(content.values()))["schema"]
        assert "tenant_id" not in _request_property_names(
            schema=media_schema,
            document=document,
        )

    case_parameters = paths["/api/v1/cases"]["get"]["parameters"]
    assert "tenant_id" not in {parameter["name"] for parameter in case_parameters}
    assert document["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert paths["/api/v1/cases"]["post"]["responses"].keys() >= {"200", "201", "409"}
    access_url_responses = paths["/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url"][
        "post"
    ]["responses"]
    assert access_url_responses.keys() >= {"200", "401", "403", "404", "500", "503"}
    content_responses = paths["/api/v1/cases/{case_id}/evidence/{evidence_id}/content"]["get"][
        "responses"
    ]
    assert content_responses.keys() >= {"200", "401", "403", "404", "500", "503"}
    assert content_responses["200"]["content"].keys() >= {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
