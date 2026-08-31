"""Configuration-driven OIDC provider adapter with an injected backchannel."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from app.platform.oidc import (
    OidcAuthorizationRequest,
    OidcCodeExchangeRequest,
    ValidatedOidcLogoutToken,
    VerifiedOidcIdentity,
)
from app.ports.oidc import OidcBackchannel, OidcProviderError


@dataclass(frozen=True, slots=True)
class OidcProviderConfiguration:
    provider_key: str
    issuer: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    redirect_uri: str
    client_secret: str | None = field(default=None, repr=False)
    scopes: tuple[str, ...] = ("openid", "email", "profile")
    allowed_algorithms: tuple[str, ...] = ("RS256",)
    groups_claim: str = "groups"
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        for name in ("provider_key", "issuer", "client_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be a non-blank string")
        for name in (
            "issuer",
            "authorization_endpoint",
            "token_endpoint",
            "jwks_uri",
            "redirect_uri",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _is_allowed_url(
                value,
                allow_insecure_http=self.allow_insecure_http,
            ):
                raise ValueError(f"{name} must be an absolute HTTPS URL")
        if self.client_secret is not None and (
            not self.client_secret or self.client_secret != self.client_secret.strip()
        ):
            raise ValueError("client_secret must be a non-blank string when configured")
        if not self.scopes or "openid" not in self.scopes:
            raise ValueError("scopes must include openid")
        if any(not scope or scope != scope.strip() for scope in self.scopes) or len(
            self.scopes
        ) != len(set(self.scopes)):
            raise ValueError("scopes must contain only non-blank values")
        if not self.allowed_algorithms or any(
            algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
            for algorithm in self.allowed_algorithms
        ):
            raise ValueError("allowed_algorithms must contain supported asymmetric algorithms")
        if len(self.allowed_algorithms) != len(set(self.allowed_algorithms)):
            raise ValueError("allowed_algorithms must be unique")
        if not self.groups_claim or self.groups_claim != self.groups_claim.strip():
            raise ValueError("groups_claim must be a non-blank string")


class StandardOidcProviderAdapter:
    """Build front-channel URLs and delegate token/JWKS work to one backchannel port."""

    def __init__(
        self,
        *,
        configuration: OidcProviderConfiguration,
        backchannel: OidcBackchannel,
    ) -> None:
        self._configuration = configuration
        self._backchannel = backchannel

    @property
    def provider_key(self) -> str:
        return self._configuration.provider_key

    def authorization_url(self, request: OidcAuthorizationRequest) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._configuration.client_id,
                "redirect_uri": self._configuration.redirect_uri,
                "scope": " ".join(self._configuration.scopes),
                "state": request.state,
                "nonce": request.nonce,
                "code_challenge": request.code_challenge,
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in self._configuration.authorization_endpoint else "?"
        return f"{self._configuration.authorization_endpoint}{separator}{query}"

    def exchange_code(self, request: OidcCodeExchangeRequest) -> VerifiedOidcIdentity:
        identity = self._backchannel.exchange_and_validate(
            token_endpoint=self._configuration.token_endpoint,
            jwks_uri=self._configuration.jwks_uri,
            issuer=self._configuration.issuer,
            client_id=self._configuration.client_id,
            client_secret=self._configuration.client_secret,
            redirect_uri=self._configuration.redirect_uri,
            allowed_algorithms=self._configuration.allowed_algorithms,
            groups_claim=self._configuration.groups_claim,
            code=request.code,
            pkce_verifier=request.pkce_verifier,
            expected_nonce=request.expected_nonce,
        )
        if identity.issuer != self._configuration.issuer:
            raise OidcProviderError("backchannel returned an identity for an unexpected issuer")
        return identity

    def validate_logout_token(self, logout_token: str) -> ValidatedOidcLogoutToken:
        return self._backchannel.validate_logout_token(
            raw_logout_token=logout_token,
            jwks_uri=self._configuration.jwks_uri,
            issuer=self._configuration.issuer,
            client_id=self._configuration.client_id,
            allowed_algorithms=self._configuration.allowed_algorithms,
        )


def _is_allowed_url(value: str, *, allow_insecure_http: bool) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in ({"http", "https"} if allow_insecure_http else {"https"})
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and parsed.fragment == ""
    )
