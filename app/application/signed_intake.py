"""Authenticate a deployment-authorized signed intake source."""

from datetime import timedelta

from app.platform.signed_intake import (
    AuthenticatedSignedIntake,
    SignedIntakeAuthenticationError,
    SignedIntakeProof,
)
from app.ports.identity import IdentityRepository
from app.ports.runtime import Clock
from app.ports.signed_intake import SignedIntakeSignatureVerifier, SignedIntakeSourceRegistry


class AuthenticateSignedIntake:
    def __init__(
        self,
        *,
        sources: SignedIntakeSourceRegistry,
        signatures: SignedIntakeSignatureVerifier,
        identities: IdentityRepository,
        clock: Clock,
        allowed_clock_skew: timedelta = timedelta(seconds=300),
    ) -> None:
        seconds = allowed_clock_skew.total_seconds()
        if seconds < 0 or seconds > 300:
            raise ValueError("signed intake clock skew must be between zero and 300 seconds")
        self._sources = sources
        self._signatures = signatures
        self._identities = identities
        self._clock = clock
        self._allowed_clock_skew_seconds = int(seconds)

    def execute(self, proof: SignedIntakeProof) -> AuthenticatedSignedIntake:
        now = self._clock.now()
        if abs(int(now.timestamp()) - proof.timestamp) > self._allowed_clock_skew_seconds:
            raise SignedIntakeAuthenticationError()
        signature_valid = self._signatures.verify(proof)
        source = self._sources.get(proof.key_id)
        if not signature_valid or source is None:
            raise SignedIntakeAuthenticationError()
        account = self._identities.get_by_tenant_and_subject(
            tenant_id=source.tenant_id,
            subject=source.actor_user_id,
        )
        if (
            account is None
            or not account.is_active
            or not account.tenant_is_active
            or account.tenant_id != source.tenant_id
            or account.user_id != source.actor_user_id
            or bool(account.roles)
        ):
            raise SignedIntakeAuthenticationError()
        return AuthenticatedSignedIntake(source=source, authenticated_at=now)


__all__ = ["AuthenticateSignedIntake"]
