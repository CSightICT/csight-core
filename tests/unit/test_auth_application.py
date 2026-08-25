"""Pure unit tests for tenant authentication application boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from app.application.auth import (
    AuthenticateUser,
    LoginCommand,
    ResolvePrincipal,
)
from app.platform.errors import AuthenticationRequiredError, InvalidCredentialsError
from app.platform.tenant import Role, UserAccount
from app.ports.security import AccessTokenClaims, InvalidTokenError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)


class FakeIdentityRepository:
    def __init__(self, account: UserAccount | None) -> None:
        self.account = account
        self.login_calls: list[tuple[str, str]] = []
        self.subject_calls: list[tuple[str, str]] = []

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        self.login_calls.append((tenant_slug, email))
        return self.account

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        self.subject_calls.append((tenant_id, subject))
        return self.account


class RecordingPasswordHasher:
    def __init__(self, *, matches: bool) -> None:
        self.matches = matches
        self.verify_calls: list[tuple[str, str | None]] = []

    def hash_password(self, password: str) -> str:
        return f"hash:{password}"

    def verify_password(self, password: str, encoded_hash: str | None) -> bool:
        self.verify_calls.append((password, encoded_hash))
        return self.matches


class FakeTokenCodec:
    def __init__(self, claims: AccessTokenClaims | None = None) -> None:
        self.claims = claims or token_claims()
        self.issue_calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.decode_error: InvalidTokenError | None = None

    def issue_token(
        self,
        *,
        subject: str,
        tenant_id: str,
        roles: tuple[str, ...],
    ) -> str:
        self.issue_calls.append((subject, tenant_id, roles))
        return "signed-access-token"

    def decode_token(self, token: str) -> AccessTokenClaims:
        del token
        if self.decode_error is not None:
            raise self.decode_error
        return self.claims


def account(
    *,
    tenant_id: str = "tenant-a",
    user_id: str = "user-a",
    roles: frozenset[Role] = frozenset({Role.REVIEWER}),
    is_active: bool = True,
    tenant_is_active: bool = True,
) -> UserAccount:
    return UserAccount(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug="tenant-a",
        email="reviewer@example.com",
        display_name="Reviewer",
        password_hash="$argon2id$not-a-real-test-hash",
        roles=roles,
        is_active=is_active,
        tenant_is_active=tenant_is_active,
    )


def token_claims(
    *,
    tenant_id: str = "tenant-a",
    subject: str = "user-a",
    roles: tuple[str, ...] = ("ADMIN",),
) -> AccessTokenClaims:
    return AccessTokenClaims(
        subject=subject,
        tenant_id=tenant_id,
        roles=roles,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        token_id="token-a",
    )


def test_login_normalizes_identifiers_preserves_password_and_issues_current_roles() -> None:
    identities = FakeIdentityRepository(account(roles=frozenset({Role.REVIEWER, Role.ADMIN})))
    passwords = RecordingPasswordHasher(matches=True)
    tokens = FakeTokenCodec()
    authenticate = AuthenticateUser(
        identities=identities,
        password_hasher=passwords,
        token_codec=tokens,
        token_ttl=timedelta(minutes=15),
    )
    command = LoginCommand(
        tenant_slug=" Tenant-A ",
        email=" Reviewer@Example.COM ",
        password=SecretStr(" password with spaces "),
    )

    result = authenticate.execute(command)

    assert identities.login_calls == [("tenant-a", "reviewer@example.com")]
    assert passwords.verify_calls == [(" password with spaces ", "$argon2id$not-a-real-test-hash")]
    assert tokens.issue_calls == [("user-a", "tenant-a", ("ADMIN", "REVIEWER"))]
    assert result.access_token == "signed-access-token"
    assert result.token_type == "bearer"
    assert result.expires_in == 900


def test_unknown_user_always_executes_dummy_password_verification() -> None:
    identities = FakeIdentityRepository(None)
    passwords = RecordingPasswordHasher(matches=False)
    authenticate = AuthenticateUser(
        identities=identities,
        password_hasher=passwords,
        token_codec=FakeTokenCodec(),
        token_ttl=timedelta(minutes=15),
    )

    with pytest.raises(InvalidCredentialsError) as captured:
        authenticate.execute(
            LoginCommand(
                tenant_slug="tenant-a",
                email="missing@example.com",
                password=SecretStr("guess"),
            )
        )

    assert captured.value.code == "INVALID_CREDENTIALS"
    assert passwords.verify_calls == [("guess", None)]


def test_login_identifiers_are_validated_after_normalization() -> None:
    with pytest.raises(PydanticValidationError, match="tenant_slug"):
        LoginCommand(
            tenant_slug="   ",
            email="reviewer@example.com",
            password=SecretStr("guess"),
        )
    with pytest.raises(PydanticValidationError, match="email"):
        LoginCommand(
            tenant_slug="tenant-a",
            email=" x ",
            password=SecretStr("guess"),
        )


@pytest.mark.parametrize(
    "candidate",
    [
        account(is_active=False),
        account(tenant_is_active=False),
        account(roles=frozenset()),
    ],
)
def test_inactive_user_or_tenant_uses_same_invalid_credentials_error(
    candidate: UserAccount,
) -> None:
    passwords = RecordingPasswordHasher(matches=True)
    authenticate = AuthenticateUser(
        identities=FakeIdentityRepository(candidate),
        password_hasher=passwords,
        token_codec=FakeTokenCodec(),
        token_ttl=timedelta(minutes=15),
    )

    with pytest.raises(InvalidCredentialsError) as captured:
        authenticate.execute(
            LoginCommand(
                tenant_slug="tenant-a",
                email=candidate.email,
                password=SecretStr("correct"),
            )
        )

    assert captured.value.code == "INVALID_CREDENTIALS"
    assert passwords.verify_calls == [("correct", candidate.password_hash)]


def test_invalid_password_uses_same_invalid_credentials_error() -> None:
    authenticate = AuthenticateUser(
        identities=FakeIdentityRepository(account()),
        password_hasher=RecordingPasswordHasher(matches=False),
        token_codec=FakeTokenCodec(),
        token_ttl=timedelta(minutes=15),
    )

    with pytest.raises(InvalidCredentialsError):
        authenticate.execute(
            LoginCommand(
                tenant_slug="tenant-a",
                email="reviewer@example.com",
                password=SecretStr("wrong"),
            )
        )


def test_resolve_principal_reloads_current_roles_instead_of_trusting_token_roles() -> None:
    current = account(roles=frozenset({Role.QUALITY_VIEWER}))
    identities = FakeIdentityRepository(current)
    resolver = ResolvePrincipal(identities=identities, token_codec=FakeTokenCodec())

    principal = resolver.execute("signed-access-token")

    assert identities.subject_calls == [("tenant-a", "user-a")]
    assert principal.user_id == current.user_id
    assert principal.tenant_id == current.tenant_id
    assert principal.roles == frozenset({Role.QUALITY_VIEWER})


def test_invalid_token_is_mapped_to_authentication_required() -> None:
    tokens = FakeTokenCodec()
    tokens.decode_error = InvalidTokenError("bad token")
    resolver = ResolvePrincipal(identities=FakeIdentityRepository(account()), token_codec=tokens)

    with pytest.raises(AuthenticationRequiredError) as captured:
        resolver.execute("invalid")

    assert captured.value.code == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        account(is_active=False),
        account(tenant_is_active=False),
        account(roles=frozenset()),
        account(tenant_id="tenant-b"),
        account(user_id="different-user"),
    ],
)
def test_missing_inactive_or_claim_mismatched_account_requires_authentication(
    candidate: UserAccount | None,
) -> None:
    resolver = ResolvePrincipal(
        identities=FakeIdentityRepository(candidate),
        token_codec=FakeTokenCodec(),
    )

    with pytest.raises(AuthenticationRequiredError) as captured:
        resolver.execute("signed-access-token")

    assert captured.value.code == "AUTHENTICATION_REQUIRED"


def test_sensitive_authentication_values_are_redacted_from_representations() -> None:
    user = account()
    command = LoginCommand(
        tenant_slug="tenant-a",
        email="reviewer@example.com",
        password=SecretStr("plain-password"),
    )

    assert "plain-password" not in repr(command)
    assert user.password_hash not in repr(user)
