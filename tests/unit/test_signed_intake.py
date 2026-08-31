"""Ed25519 signed Case intake authentication and HTTP boundary tests."""

import base64
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from app.adapters.security.signed_intake_signatures import (
    ConfiguredSignedIntakeSourceRegistry,
    Ed25519SignedIntakeSignatureVerifier,
    SignedIntakeKeyConfigurationError,
    load_ed25519_public_key_file,
)
from app.application.cases import CreateCaseResult, CreateSignedIntakeCaseCommand
from app.application.signed_intake import AuthenticateSignedIntake
from app.bootstrap.settings import Settings
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.main import create_app
from app.platform.case import Case, CaseSourceScope
from app.platform.signed_intake import (
    AuthenticatedSignedIntake,
    SignedIntakeAuthenticationError,
    SignedIntakeProof,
    SignedIntakeSource,
)
from app.platform.tenant import Role, UserAccount

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 3, 4, 5, tzinfo=UTC)
TENANT_ID = "00000000-0000-4000-8000-000000000101"
ACTOR_ID = "00000000-0000-4000-8000-000000000102"
PATH = "/api/v1/integrations/cases"


class StaticClock:
    def now(self) -> datetime:
        return NOW


class FakeIdentities:
    def __init__(self, account: UserAccount | None) -> None:
        self.account = account

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        del tenant_slug, email
        return None

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        if self.account is None:
            return None
        if self.account.tenant_id != tenant_id or self.account.user_id != subject:
            return None
        return self.account


class RecordingCreateSignedCase:
    def __init__(self) -> None:
        self.calls: list[CreateSignedIntakeCaseCommand] = []

    def execute(
        self,
        *,
        authenticated: AuthenticatedSignedIntake,
        command: CreateSignedIntakeCaseCommand,
    ) -> CreateCaseResult:
        source = authenticated.source
        self.calls.append(command)
        case = Case.create(
            case_id="00000000-0000-4000-8000-000000000201",
            tenant_id=source.tenant_id,
            order_ref=command.case.order_ref,
            product_ref=command.case.product_ref,
            customer_message=command.case.customer_message,
            requested_action=command.case.requested_action,
            attributes=command.case.attributes,
            created_by=source.actor_user_id,
            now=NOW,
            source_scope=CaseSourceScope.PILOT_LIVE,
            source_provenance=source.provenance,
        )
        return CreateCaseResult(case=case)


def _source() -> SignedIntakeSource:
    return SignedIntakeSource(
        key_id="crm-key-1",
        source_id="customer-crm",
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        provenance="signed/crm/v1",
    )


def _account(*, roles: frozenset[Role] = frozenset()) -> UserAccount:
    return UserAccount(
        user_id=ACTOR_ID,
        tenant_id=TENANT_ID,
        tenant_slug="pilot-a",
        email="intake@pilot-a.invalid",
        display_name="Signed intake service",
        password_hash="disabled-service-account",
        roles=roles,
        is_active=True,
        tenant_is_active=True,
    )


def _proof(
    *,
    private_key: Ed25519PrivateKey,
    body: bytes,
    timestamp: int | None = None,
    event_id: str = "event-1",
) -> SignedIntakeProof:
    resolved_timestamp = timestamp if timestamp is not None else int(NOW.timestamp())
    body_sha256 = hashlib.sha256(body).hexdigest()
    unsigned = SignedIntakeProof(
        method="POST",
        path=PATH,
        key_id="crm-key-1",
        event_id=event_id,
        timestamp=resolved_timestamp,
        body_sha256=body_sha256,
        signature_base64=base64.b64encode(bytes(64)).decode(),
    )
    return SignedIntakeProof(
        method="POST",
        path=PATH,
        key_id="crm-key-1",
        event_id=event_id,
        timestamp=resolved_timestamp,
        body_sha256=body_sha256,
        signature_base64=base64.b64encode(private_key.sign(unsigned.canonical_bytes())).decode(),
    )


def _authenticator(private_key: Ed25519PrivateKey) -> AuthenticateSignedIntake:
    return AuthenticateSignedIntake(
        sources=ConfiguredSignedIntakeSourceRegistry({"crm-key-1": _source()}),
        signatures=Ed25519SignedIntakeSignatureVerifier({"crm-key-1": private_key.public_key()}),
        identities=FakeIdentities(_account()),
        clock=StaticClock(),
    )


def _body(**extra: object) -> bytes:
    payload: dict[str, object] = {
        "schema_version": "signed_case_intake/1.0.0",
        "order_ref": "ORD-100",
        "product_ref": "SKU-200",
        "customer_message": "The delivered item appears damaged.",
        "requested_action": "EXCHANGE",
        "attributes": {"channel": "crm"},
    }
    payload.update(extra)
    return json.dumps(payload, separators=(",", ":")).encode()


def _headers(proof: SignedIntakeProof) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-CSight-Intake-Key-Id": proof.key_id,
        "X-CSight-Intake-Event-Id": proof.event_id,
        "X-CSight-Intake-Timestamp": str(proof.timestamp),
        "X-CSight-Intake-Signature": proof.signature_base64,
    }


def test_authentication_rejects_stale_signature_and_privileged_actor() -> None:
    private_key = Ed25519PrivateKey.generate()
    body = _body()
    stale = _proof(
        private_key=private_key,
        body=body,
        timestamp=int((NOW - timedelta(seconds=301)).timestamp()),
    )
    with pytest.raises(SignedIntakeAuthenticationError):
        _authenticator(private_key).execute(stale)

    privileged = AuthenticateSignedIntake(
        sources=ConfiguredSignedIntakeSourceRegistry({"crm-key-1": _source()}),
        signatures=Ed25519SignedIntakeSignatureVerifier({"crm-key-1": private_key.public_key()}),
        identities=FakeIdentities(_account(roles=frozenset({Role.ADMIN}))),
        clock=StaticClock(),
    )
    with pytest.raises(SignedIntakeAuthenticationError):
        privileged.execute(_proof(private_key=private_key, body=body))


def test_public_key_loader_rejects_writable_or_symlinked_key_files(tmp_path: Path) -> None:
    public_key_file = tmp_path / "intake-public.pem"
    public_key_file.write_bytes(
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    public_key_file.chmod(0o600)
    assert load_ed25519_public_key_file(public_key_file) is not None

    public_key_file.chmod(0o622)
    with pytest.raises(SignedIntakeKeyConfigurationError, match="must not be"):
        load_ed25519_public_key_file(public_key_file)

    public_key_file.chmod(0o600)
    symlink = tmp_path / "linked-public.pem"
    symlink.symlink_to(public_key_file)
    with pytest.raises(SignedIntakeKeyConfigurationError, match="non-symlink"):
        load_ed25519_public_key_file(symlink)


def test_http_valid_signature_creates_one_pilot_live_case() -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=128 * 1024,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    body = _body()
    proof = _proof(private_key=private_key, body=body)

    response = client.post(PATH, content=body, headers=_headers(proof))

    assert response.status_code == 201
    assert response.json()["source_scope"] == "PILOT_LIVE"
    assert response.json()["source_event_id"] == "event-1"
    assert response.headers["Cache-Control"] == "no-store"
    assert len(creator.calls) == 1


def test_http_declared_oversize_is_413_and_makes_zero_writes() -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=64,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    body = _body()
    proof = _proof(private_key=private_key, body=body)

    response = client.post(PATH, content=body, headers=_headers(proof))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert creator.calls == []


def test_http_chunked_oversize_is_413_and_makes_zero_writes() -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=64,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    body = _body()
    proof = _proof(private_key=private_key, body=body)
    headers = _headers(proof)
    headers["Transfer-Encoding"] = "chunked"

    def chunks() -> Iterator[bytes]:
        yield body[:48]
        yield body[48:96]
        yield body[96:]

    response = client.post(PATH, content=chunks(), headers=headers)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert creator.calls == []


def test_http_validation_error_never_exposes_customer_or_attribute_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=128 * 1024,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    customer_secret = "CUSTOMER-SECRET-DO-NOT-ECHO"
    attribute_secret = "ATTRIBUTE-SECRET-DO-NOT-ECHO"
    body = _body(
        customer_message=customer_secret + "x" * 20_001,
        attributes={"private_notes": attribute_secret + "y" * 65_536},
    )
    proof = _proof(private_key=private_key, body=body)

    response = client.post(PATH, content=body, headers=_headers(proof))

    assert response.status_code == 422
    response_text = response.text
    assert customer_secret not in response_text
    assert attribute_secret not in response_text
    assert customer_secret not in caplog.text
    assert attribute_secret not in caplog.text
    errors = response.json()["error"]["details"]["errors"]
    assert errors
    assert all(set(item) == {"type", "location", "message"} for item in errors)
    assert all(item["message"] == "Invalid value." for item in errors)
    assert creator.calls == []


@pytest.mark.parametrize("failure", ["tampered", "stale"])
def test_http_tampered_or_stale_signature_makes_zero_writes(failure: str) -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=128 * 1024,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    signed_body = _body()
    timestamp = (
        int((NOW - timedelta(seconds=301)).timestamp())
        if failure == "stale"
        else int(NOW.timestamp())
    )
    proof = _proof(private_key=private_key, body=signed_body, timestamp=timestamp)
    sent_body = _body(customer_message="tampered") if failure == "tampered" else signed_body

    response = client.post(PATH, content=sent_body, headers=_headers(proof))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SIGNED_INTAKE_AUTHENTICATION_FAILED"
    assert creator.calls == []


@pytest.mark.parametrize("forbidden_field", ["tenant_id", "source_scope"])
def test_http_body_cannot_select_tenant_or_source_scope(forbidden_field: str) -> None:
    private_key = Ed25519PrivateKey.generate()
    creator = RecordingCreateSignedCase()
    services = SignedIntakeServiceContainer(
        authenticate=_authenticator(private_key),
        create_case=creator,
        max_body_bytes=128 * 1024,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )
    body = _body(**{forbidden_field: "PILOT_LIVE"})
    proof = _proof(private_key=private_key, body=body)

    response = client.post(PATH, content=body, headers=_headers(proof))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert creator.calls == []
