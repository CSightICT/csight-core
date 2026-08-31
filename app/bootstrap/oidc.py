"""Composition root for enterprise OIDC login and server-side sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepositoryFactoryAdapter
from app.adapters.persistence.oidc_sessions import SQLAlchemyOidcRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.runtime import UtcClock, Uuid4Generator
from app.adapters.security.oidc_backchannel import Urllib3OidcBackchannel
from app.adapters.security.oidc_identity import ConfiguredOidcIdentityMapper, OidcGroupTarget
from app.adapters.security.oidc_provider import (
    OidcProviderConfiguration,
    StandardOidcProviderAdapter,
)
from app.adapters.security.oidc_tokens import SystemSecureTokenGenerator
from app.application.oidc import OidcSessionService
from app.bootstrap.settings import Settings
from app.interface.http.oidc_router import OidcCookieConfiguration
from app.platform.oidc import ReturnPathAllowlist


class OidcConfigurationError(RuntimeError):
    """Raised without provider credentials when OIDC configuration is incomplete."""


@dataclass(frozen=True, slots=True)
class OidcRuntime:
    service: OidcSessionService
    cookie: OidcCookieConfiguration


def oidc_is_configured(settings: Settings) -> bool:
    return settings.oidc_is_configured


def build_oidc_runtime(settings: Settings) -> OidcRuntime:
    missing = settings.oidc_configuration_missing
    if missing:
        raise OidcConfigurationError(f"OIDC configuration is incomplete: {', '.join(missing)}")

    engine = get_engine(settings)
    session_factory = create_session_factory(engine)
    identities = SQLAlchemyIdentityRepositoryFactoryAdapter(session_factory)
    mappings = {
        group: OidcGroupTarget(
            tenant_slug=target.tenant_slug,
            allowed_roles=target.allowed_roles,
        )
        for group, target in settings.oidc_group_mappings.items()
    }
    identity_mapper = ConfiguredOidcIdentityMapper(
        identities=identities,
        group_mappings=mappings,
    )
    backchannel = Urllib3OidcBackchannel(
        identity_mapper=identity_mapper,
        connect_timeout_seconds=settings.oidc_connect_timeout_seconds,
        read_timeout_seconds=settings.oidc_read_timeout_seconds,
        max_response_bytes=settings.oidc_max_response_bytes,
        jwks_cache_seconds=settings.oidc_jwks_cache_seconds,
        clock_skew_seconds=settings.oidc_clock_skew_seconds,
        tls_verify=settings.oidc_tls_verify,
    )
    provider = StandardOidcProviderAdapter(
        configuration=OidcProviderConfiguration(
            provider_key=settings.oidc_provider_key,
            issuer=_required_url(settings.oidc_issuer, "OIDC_ISSUER"),
            client_id=_required(settings.oidc_client_id, "OIDC_CLIENT_ID"),
            client_secret=settings.oidc_client_secret_value,
            authorization_endpoint=_required_url(
                settings.oidc_authorization_endpoint,
                "OIDC_AUTHORIZATION_ENDPOINT",
            ),
            token_endpoint=_required_url(settings.oidc_token_endpoint, "OIDC_TOKEN_ENDPOINT"),
            jwks_uri=_required_url(settings.oidc_jwks_uri, "OIDC_JWKS_URI"),
            redirect_uri=_required_url(settings.oidc_redirect_uri, "OIDC_REDIRECT_URI"),
            scopes=settings.oidc_scopes,
            allowed_algorithms=settings.oidc_allowed_algorithms,
            groups_claim=settings.oidc_groups_claim,
            allow_insecure_http=settings.oidc_allow_insecure_http,
        ),
        backchannel=backchannel,
    )
    repository = SQLAlchemyOidcRepository(session_factory)
    service = OidcSessionService(
        login_transactions=repository,
        sessions=repository,
        identities=identities,
        provider=provider,
        secure_tokens=SystemSecureTokenGenerator(),
        clock=UtcClock(),
        id_generator=Uuid4Generator(),
        return_paths=ReturnPathAllowlist(settings.oidc_return_path_allowlist),
        absolute_timeout=timedelta(seconds=settings.oidc_session_absolute_timeout_seconds),
        idle_timeout=timedelta(seconds=settings.oidc_session_idle_timeout_seconds),
        expiry_warning=timedelta(seconds=settings.oidc_session_expiry_warning_seconds),
    )
    return OidcRuntime(
        service=service,
        cookie=OidcCookieConfiguration(
            name=settings.oidc_cookie_name,
            secure=settings.oidc_cookie_secure,
            same_site=settings.oidc_cookie_same_site,
        ),
    )


def _required(value: str | None, name: str) -> str:
    if not value:
        raise OidcConfigurationError(f"{name} is required")
    return value


def _required_url(value: object | None, name: str) -> str:
    if value is None:
        raise OidcConfigurationError(f"{name} is required")
    return str(value)


__all__ = [
    "OidcConfigurationError",
    "OidcRuntime",
    "build_oidc_runtime",
    "oidc_is_configured",
]
