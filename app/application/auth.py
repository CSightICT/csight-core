"""Tenant-scoped authentication and access-token principal resolution."""

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.platform.errors import AuthenticationRequiredError, InvalidCredentialsError
from app.platform.tenant import Principal
from app.ports.identity import IdentityRepository
from app.ports.security import AccessTokenCodec, PasswordHasher, SecurityError


class LoginCommand(BaseModel):
    """Credentials whose password representation remains redacted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_slug: str = Field(min_length=1, max_length=63)
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("tenant_slug", "email", mode="before")
    @classmethod
    def normalize_login_identifier(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().lower()


class LoginResult(BaseModel):
    """Bearer access token and its configured lifetime in seconds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)


class AuthenticateUser:
    """Validate tenant credentials and issue one short-lived access token."""

    def __init__(
        self,
        *,
        identities: IdentityRepository,
        password_hasher: PasswordHasher,
        token_codec: AccessTokenCodec,
        token_ttl: timedelta,
    ) -> None:
        ttl_seconds = token_ttl.total_seconds()
        if ttl_seconds < 1 or not ttl_seconds.is_integer():
            raise ValueError("token_ttl must be a positive whole number of seconds")
        self._identities = identities
        self._password_hasher = password_hasher
        self._token_codec = token_codec
        self._expires_in = int(ttl_seconds)

    def execute(self, command: LoginCommand) -> LoginResult:
        account = self._identities.find_for_login(
            tenant_slug=command.tenant_slug,
            email=command.email,
        )
        password_matches = self._password_hasher.verify_password(
            command.password.get_secret_value(),
            account.password_hash if account is not None else None,
        )
        if account is None or not password_matches or not account.can_authenticate:
            raise InvalidCredentialsError()

        access_token = self._token_codec.issue_token(
            subject=account.user_id,
            tenant_id=account.tenant_id,
            roles=tuple(sorted(role.value for role in account.roles)),
        )
        return LoginResult(access_token=access_token, expires_in=self._expires_in)


class ResolvePrincipal:
    """Validate a token and rehydrate its active user and current roles."""

    def __init__(
        self,
        *,
        identities: IdentityRepository,
        token_codec: AccessTokenCodec,
    ) -> None:
        self._identities = identities
        self._token_codec = token_codec

    def execute(self, token: str) -> Principal:
        try:
            claims = self._token_codec.decode_token(token)
        except SecurityError as error:
            raise AuthenticationRequiredError() from error

        account = self._identities.get_by_tenant_and_subject(
            tenant_id=claims.tenant_id,
            subject=claims.subject,
        )
        if (
            account is None
            or not account.can_authenticate
            or account.tenant_id != claims.tenant_id
            or account.user_id != claims.subject
        ):
            raise AuthenticationRequiredError()

        return Principal(
            user_id=account.user_id,
            tenant_id=account.tenant_id,
            email=account.email,
            display_name=account.display_name,
            roles=account.roles,
        )
