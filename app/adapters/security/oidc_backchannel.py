"""Bounded urllib3 OIDC token exchange and PyJWT/JWKS validation adapter."""

from __future__ import annotations

import base64
import hmac
import json
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Protocol, cast
from urllib.parse import urlencode

import jwt
import urllib3
from jwt import InvalidSignatureError, InvalidTokenError
from urllib3 import Timeout
from urllib3.exceptions import HTTPError

from app.platform.oidc import (
    ValidatedOidcClaims,
    ValidatedOidcLogoutToken,
    VerifiedOidcIdentity,
)
from app.ports.oidc import (
    OidcClaimsIdentityMapper,
    OidcProviderError,
    OidcProviderTemporarilyUnavailableError,
)

_ASYMMETRIC_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class _HttpResponse(Protocol):
    status: int

    def read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
    ) -> bytes: ...

    def release_conn(self) -> None: ...

    def close(self) -> None: ...


class _HttpPool(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: dict[str, str],
        timeout: Timeout,
        retries: bool,
        preload_content: bool,
    ) -> _HttpResponse: ...


@dataclass(frozen=True, slots=True)
class _JwksCacheEntry:
    document: dict[str, object]
    expires_at: float


class Urllib3OidcBackchannel:
    """Exchange one code and validate the resulting ID token without leaking secrets."""

    def __init__(
        self,
        *,
        identity_mapper: OidcClaimsIdentityMapper,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 5.0,
        max_response_bytes: int = 1024 * 1024,
        jwks_cache_seconds: int = 300,
        clock_skew_seconds: int = 30,
        tls_verify: bool = True,
        http_pool: _HttpPool | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < connect_timeout_seconds <= 30:
            raise ValueError("connect_timeout_seconds must be between 0 and 30")
        if not 0 < read_timeout_seconds <= 60:
            raise ValueError("read_timeout_seconds must be between 0 and 60")
        if not 1024 <= max_response_bytes <= 4 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 KiB and 4 MiB")
        if not 1 <= jwks_cache_seconds <= 86400:
            raise ValueError("jwks_cache_seconds must be between 1 and 86400")
        if not 0 <= clock_skew_seconds <= 300:
            raise ValueError("clock_skew_seconds must be between 0 and 300")
        self._identity_mapper = identity_mapper
        self._timeout = Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
        )
        self._max_response_bytes = max_response_bytes
        self._jwks_cache_seconds = jwks_cache_seconds
        self._clock_skew_seconds = clock_skew_seconds
        self._monotonic = monotonic
        self._pool = http_pool or cast(
            _HttpPool,
            urllib3.PoolManager(
                cert_reqs=ssl.CERT_REQUIRED if tls_verify else ssl.CERT_NONE,
            ),
        )
        self._jwks_cache: dict[str, _JwksCacheEntry] = {}
        self._jwks_lock = RLock()

    def exchange_and_validate(
        self,
        *,
        token_endpoint: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        allowed_algorithms: tuple[str, ...],
        groups_claim: str,
        code: str,
        pkce_verifier: str,
        expected_nonce: str,
    ) -> VerifiedOidcIdentity:
        algorithms = self._validated_algorithms(allowed_algorithms)
        token_payload = self._exchange_code(
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=code,
            pkce_verifier=pkce_verifier,
        )
        raw_id_token = token_payload.get("id_token")
        if not isinstance(raw_id_token, str) or not 1 <= len(raw_id_token) <= 65536:
            raise OidcProviderError("OIDC token response did not contain a bounded ID token")
        claims = self._validate_id_token(
            raw_id_token=raw_id_token,
            jwks_uri=jwks_uri,
            issuer=issuer,
            client_id=client_id,
            allowed_algorithms=algorithms,
            groups_claim=groups_claim,
            expected_nonce=expected_nonce,
        )
        return self._identity_mapper.map_identity(claims)

    def validate_logout_token(
        self,
        *,
        raw_logout_token: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        allowed_algorithms: tuple[str, ...],
    ) -> ValidatedOidcLogoutToken:
        """Validate one signed OIDC Back-Channel Logout token without logging it."""

        if not 1 <= len(raw_logout_token) <= 65536:
            raise OidcProviderError("OIDC logout token size is invalid")
        algorithms = self._validated_algorithms(allowed_algorithms)
        try:
            header = jwt.get_unverified_header(raw_logout_token)
        except InvalidTokenError as error:
            raise OidcProviderError("OIDC logout token header is invalid") from error
        algorithm = header.get("alg")
        key_id = header.get("kid")
        token_type = header.get("typ")
        if (
            not isinstance(algorithm, str)
            or algorithm not in algorithms
            or not isinstance(key_id, str)
            or not key_id
            or token_type not in {None, "JWT", "logout+jwt"}
        ):
            raise OidcProviderError("OIDC logout token header is not allowed")

        signing_key = self._signing_key(
            jwks_uri=jwks_uri,
            key_id=key_id,
            algorithm=algorithm,
            force_refresh=False,
        )
        try:
            decoded = self._decode_logout_token(
                raw_logout_token=raw_logout_token,
                signing_key=signing_key,
                algorithm=algorithm,
                issuer=issuer,
                client_id=client_id,
            )
        except InvalidSignatureError:
            refreshed_key = self._signing_key(
                jwks_uri=jwks_uri,
                key_id=key_id,
                algorithm=algorithm,
                force_refresh=True,
            )
            try:
                decoded = self._decode_logout_token(
                    raw_logout_token=raw_logout_token,
                    signing_key=refreshed_key,
                    algorithm=algorithm,
                    issuer=issuer,
                    client_id=client_id,
                )
            except InvalidTokenError as error:
                raise OidcProviderError("OIDC logout token validation failed") from error
        except InvalidTokenError as error:
            raise OidcProviderError("OIDC logout token validation failed") from error

        events = decoded.get("events")
        subject = decoded.get("sub")
        session_id = decoded.get("sid")
        jwt_id = decoded.get("jti")
        if (
            not isinstance(events, dict)
            or not isinstance(events.get(_BACKCHANNEL_LOGOUT_EVENT), dict)
            or "nonce" in decoded
            or (subject is not None and (not isinstance(subject, str) or not subject))
            or (session_id is not None and (not isinstance(session_id, str) or not session_id))
            or (subject is None and session_id is None)
            or not isinstance(jwt_id, str)
            or not jwt_id
        ):
            raise OidcProviderError("OIDC logout token claims are invalid")
        try:
            return ValidatedOidcLogoutToken(
                issuer=issuer,
                subject=subject,
                session_id=session_id,
                jwt_id=jwt_id,
            )
        except ValueError as error:
            raise OidcProviderError("OIDC logout token claims are invalid") from error

    def _exchange_code(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        code: str,
        pkce_verifier: str,
    ) -> dict[str, object]:
        fields = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": pkce_verifier,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if client_secret is not None:
            basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"
        return self._request_json(
            method="POST",
            url=token_endpoint,
            body=urlencode(fields).encode("ascii"),
            headers=headers,
        )

    def _validate_id_token(
        self,
        *,
        raw_id_token: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        allowed_algorithms: tuple[str, ...],
        groups_claim: str,
        expected_nonce: str,
    ) -> ValidatedOidcClaims:
        try:
            header = jwt.get_unverified_header(raw_id_token)
        except InvalidTokenError as error:
            raise OidcProviderError("OIDC ID token header is invalid") from error
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if (
            not isinstance(algorithm, str)
            or algorithm not in allowed_algorithms
            or not isinstance(key_id, str)
            or not key_id
        ):
            raise OidcProviderError("OIDC ID token algorithm or key ID is not allowed")

        signing_key = self._signing_key(
            jwks_uri=jwks_uri,
            key_id=key_id,
            algorithm=algorithm,
            force_refresh=False,
        )
        try:
            decoded = self._decode(
                raw_id_token=raw_id_token,
                signing_key=signing_key,
                algorithm=algorithm,
                issuer=issuer,
                client_id=client_id,
            )
        except InvalidSignatureError:
            refreshed_key = self._signing_key(
                jwks_uri=jwks_uri,
                key_id=key_id,
                algorithm=algorithm,
                force_refresh=True,
            )
            try:
                decoded = self._decode(
                    raw_id_token=raw_id_token,
                    signing_key=refreshed_key,
                    algorithm=algorithm,
                    issuer=issuer,
                    client_id=client_id,
                )
            except InvalidTokenError as error:
                raise OidcProviderError("OIDC ID token validation failed") from error
        except InvalidTokenError as error:
            raise OidcProviderError("OIDC ID token validation failed") from error

        self._validate_authorized_party(decoded, client_id=client_id)
        nonce = decoded.get("nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(
            nonce.encode("utf-8"),
            expected_nonce.encode("utf-8"),
        ):
            raise OidcProviderError("OIDC nonce validation failed")
        subject = decoded.get("sub")
        session_id = decoded.get("sid")
        email = decoded.get("email")
        email_verified = decoded.get("email_verified")
        raw_groups = decoded.get(groups_claim)
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(email, str)
            or not email
            or not isinstance(email_verified, bool)
            or not isinstance(raw_groups, list)
            or not raw_groups
            or any(not isinstance(group, str) for group in raw_groups)
            or (session_id is not None and (not isinstance(session_id, str) or not session_id))
        ):
            raise OidcProviderError("OIDC ID token identity claims are invalid")
        try:
            return ValidatedOidcClaims(
                issuer=issuer,
                subject=subject,
                session_id=session_id,
                email=email,
                email_verified=email_verified,
                nonce=nonce,
                groups=tuple(cast(list[str], raw_groups)),
            )
        except ValueError as error:
            raise OidcProviderError("OIDC ID token identity claims are invalid") from error

    def _decode(
        self,
        *,
        raw_id_token: str,
        signing_key: jwt.PyJWK,
        algorithm: str,
        issuer: str,
        client_id: str,
    ) -> dict[str, object]:
        decoded = jwt.decode(
            raw_id_token,
            key=signing_key,
            algorithms=[algorithm],
            audience=client_id,
            issuer=issuer,
            leeway=self._clock_skew_seconds,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub", "nonce", "email"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        return cast(dict[str, object], decoded)

    def _decode_logout_token(
        self,
        *,
        raw_logout_token: str,
        signing_key: jwt.PyJWK,
        algorithm: str,
        issuer: str,
        client_id: str,
    ) -> dict[str, object]:
        decoded = jwt.decode(
            raw_logout_token,
            key=signing_key,
            algorithms=[algorithm],
            audience=client_id,
            issuer=issuer,
            leeway=self._clock_skew_seconds,
            options={
                "require": ["exp", "iat", "iss", "aud", "jti", "events"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        return cast(dict[str, object], decoded)

    @staticmethod
    def _validate_authorized_party(decoded: dict[str, object], *, client_id: str) -> None:
        audience = decoded.get("aud")
        if isinstance(audience, list) and len(audience) > 1 and decoded.get("azp") != client_id:
            raise OidcProviderError("OIDC authorized party claim is invalid")

    def _signing_key(
        self,
        *,
        jwks_uri: str,
        key_id: str,
        algorithm: str,
        force_refresh: bool,
    ) -> jwt.PyJWK:
        document = self._jwks_document(jwks_uri, force_refresh=force_refresh)
        keys = document.get("keys")
        if not isinstance(keys, list):
            raise OidcProviderError("OIDC JWKS document is invalid")
        matches: list[dict[str, object]] = []
        for candidate in keys:
            if not isinstance(candidate, dict) or candidate.get("kid") != key_id:
                continue
            use = candidate.get("use")
            key_ops = candidate.get("key_ops")
            if use not in {None, "sig"}:
                continue
            if key_ops is not None and (not isinstance(key_ops, list) or "verify" not in key_ops):
                continue
            if candidate.get("alg") not in {None, algorithm}:
                continue
            matches.append(cast(dict[str, object], candidate))
        if not matches and not force_refresh:
            return self._signing_key(
                jwks_uri=jwks_uri,
                key_id=key_id,
                algorithm=algorithm,
                force_refresh=True,
            )
        if len(matches) != 1:
            raise OidcProviderError("OIDC signing key could not be selected uniquely")
        try:
            return jwt.PyJWK.from_dict(matches[0], algorithm=algorithm)
        except (InvalidTokenError, ValueError, TypeError) as error:
            raise OidcProviderError("OIDC signing key is invalid") from error

    def _jwks_document(self, jwks_uri: str, *, force_refresh: bool) -> dict[str, object]:
        now = self._monotonic()
        with self._jwks_lock:
            cached = self._jwks_cache.get(jwks_uri)
            if not force_refresh and cached is not None and now < cached.expires_at:
                return cached.document
            document = self._request_json(
                method="GET",
                url=jwks_uri,
                body=None,
                headers={"Accept": "application/json"},
            )
            self._jwks_cache[jwks_uri] = _JwksCacheEntry(
                document=document,
                expires_at=now + self._jwks_cache_seconds,
            )
            return document

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> dict[str, object]:
        try:
            response = self._pool.request(
                method,
                url,
                body=body,
                headers=headers,
                timeout=self._timeout,
                retries=False,
                preload_content=False,
            )
        except (HTTPError, OSError) as error:
            raise OidcProviderTemporarilyUnavailableError("OIDC provider request failed") from error
        reusable = False
        try:
            status_code = response.status
            raw_body = response.read(
                self._max_response_bytes + 1,
                decode_content=True,
                cache_content=False,
            )
            reusable = len(raw_body) <= self._max_response_bytes
        except (HTTPError, OSError) as error:
            raise OidcProviderTemporarilyUnavailableError(
                "OIDC provider response could not be read"
            ) from error
        finally:
            if reusable:
                response.release_conn()
            else:
                response.close()
        if status_code in _RETRYABLE_STATUS_CODES:
            raise OidcProviderTemporarilyUnavailableError(
                "OIDC provider returned a retryable status"
            )
        if status_code != 200:
            raise OidcProviderError("OIDC provider rejected the request")
        if not reusable:
            raise OidcProviderError("OIDC provider response exceeded the configured bound")
        try:
            parsed = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OidcProviderError("OIDC provider response was not valid JSON") from error
        if not isinstance(parsed, dict):
            raise OidcProviderError("OIDC provider response must be a JSON object")
        return cast(dict[str, object], parsed)

    @staticmethod
    def _validated_algorithms(algorithms: tuple[str, ...]) -> tuple[str, ...]:
        if (
            not algorithms
            or len(algorithms) != len(set(algorithms))
            or any(algorithm not in _ASYMMETRIC_ALGORITHMS for algorithm in algorithms)
        ):
            raise OidcProviderError("OIDC algorithm allowlist is invalid")
        return algorithms


__all__ = ["Urllib3OidcBackchannel"]
