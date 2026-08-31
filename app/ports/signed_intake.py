"""Technology-neutral ports for signed Case intake authentication."""

from typing import Protocol

from app.platform.signed_intake import SignedIntakeProof, SignedIntakeSource


class SignedIntakeSourceRegistry(Protocol):
    def get(self, key_id: str) -> SignedIntakeSource | None: ...


class SignedIntakeSignatureVerifier(Protocol):
    def verify(self, proof: SignedIntakeProof) -> bool: ...


__all__ = ["SignedIntakeSignatureVerifier", "SignedIntakeSourceRegistry"]
