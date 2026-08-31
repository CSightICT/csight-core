"""Ed25519 verification for raw-body-bound signed intake requests."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from app.platform.signed_intake import SignedIntakeProof, SignedIntakeSource

_MAX_PUBLIC_KEY_BYTES = 4096
_DUMMY_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(bytes.fromhex("11" * 32))


class SignedIntakeKeyConfigurationError(RuntimeError):
    """Raised without key material when a configured verification key is unsafe."""


class ConfiguredSignedIntakeSourceRegistry:
    def __init__(self, sources: Mapping[str, SignedIntakeSource]) -> None:
        self._sources = dict(sources)

    def get(self, key_id: str) -> SignedIntakeSource | None:
        return self._sources.get(key_id)


class Ed25519SignedIntakeSignatureVerifier:
    def __init__(self, public_keys: Mapping[str, Ed25519PublicKey]) -> None:
        if not public_keys:
            raise SignedIntakeKeyConfigurationError("at least one signed intake key is required")
        self._public_keys = dict(public_keys)

    def verify(self, proof: SignedIntakeProof) -> bool:
        public_key = self._public_keys.get(proof.key_id, _DUMMY_PUBLIC_KEY)
        try:
            public_key.verify(proof.signature_bytes, proof.canonical_bytes())
        except InvalidSignature:
            return False
        return proof.key_id in self._public_keys


def load_ed25519_public_key_file(path: Path) -> Ed25519PublicKey:
    """Open one non-symlink verification key without a check/open race."""

    try:
        metadata = path.lstat()
    except OSError as error:
        raise SignedIntakeKeyConfigurationError(
            "a signed intake public key file is unavailable"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SignedIntakeKeyConfigurationError(
            "signed intake public keys must be regular non-symlink files"
        )
    if metadata.st_mode & 0o022:
        raise SignedIntakeKeyConfigurationError(
            "signed intake public key files must not be group or world writable"
        )
    if not 1 <= metadata.st_size <= _MAX_PUBLIC_KEY_BYTES:
        raise SignedIntakeKeyConfigurationError("a signed intake public key size is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
            or opened.st_size != metadata.st_size
        ):
            raise SignedIntakeKeyConfigurationError(
                "a signed intake public key changed while being opened"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            public_key_pem = handle.read(_MAX_PUBLIC_KEY_BYTES + 1)
    finally:
        os.close(descriptor)
    try:
        loaded = load_pem_public_key(public_key_pem)
    except (TypeError, ValueError) as error:
        raise SignedIntakeKeyConfigurationError(
            "a signed intake public key could not be parsed"
        ) from error
    if not isinstance(loaded, Ed25519PublicKey):
        raise SignedIntakeKeyConfigurationError("signed intake public keys must be Ed25519")
    return loaded


__all__ = [
    "ConfiguredSignedIntakeSourceRegistry",
    "Ed25519SignedIntakeSignatureVerifier",
    "SignedIntakeKeyConfigurationError",
    "load_ed25519_public_key_file",
]
