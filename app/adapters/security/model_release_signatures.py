"""Ed25519 verification for signed, content-addressed LLM release manifests."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from app.platform.model_activation import SignedLLMReleaseManifest

_MAX_PUBLIC_KEY_BYTES = 4096


class ModelReleaseKeyConfigurationError(RuntimeError):
    """Raised without key material when the pinned verification key is unsafe."""


class Ed25519ModelReleaseSignatureVerifier:
    def __init__(self, *, public_key: Ed25519PublicKey, expected_key_id: str) -> None:
        normalized_key_id = expected_key_id.strip()
        if not normalized_key_id:
            raise ModelReleaseKeyConfigurationError("model release signing key ID is required")
        self._public_key = public_key
        self._expected_key_id = normalized_key_id

    @classmethod
    def from_pem_bytes(
        cls,
        *,
        public_key_pem: bytes,
        expected_key_id: str,
    ) -> Ed25519ModelReleaseSignatureVerifier:
        if not 1 <= len(public_key_pem) <= _MAX_PUBLIC_KEY_BYTES:
            raise ModelReleaseKeyConfigurationError("model release public key size is invalid")
        try:
            loaded = load_pem_public_key(public_key_pem)
        except (TypeError, ValueError) as error:
            raise ModelReleaseKeyConfigurationError(
                "model release public key could not be parsed"
            ) from error
        if not isinstance(loaded, Ed25519PublicKey):
            raise ModelReleaseKeyConfigurationError("model release public key must be Ed25519")
        return cls(public_key=loaded, expected_key_id=expected_key_id)

    @classmethod
    def from_file(
        cls,
        *,
        public_key_file: Path,
        expected_key_id: str,
    ) -> Ed25519ModelReleaseSignatureVerifier:
        try:
            metadata = public_key_file.lstat()
        except OSError as error:
            raise ModelReleaseKeyConfigurationError(
                "model release public key file is unavailable"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ModelReleaseKeyConfigurationError(
                "model release public key must be a regular non-symlink file"
            )
        if metadata.st_mode & 0o022:
            raise ModelReleaseKeyConfigurationError(
                "model release public key file must not be group or world writable"
            )
        if not 1 <= metadata.st_size <= _MAX_PUBLIC_KEY_BYTES:
            raise ModelReleaseKeyConfigurationError("model release public key size is invalid")

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(public_key_file, flags)
        except OSError as error:
            raise ModelReleaseKeyConfigurationError(
                "model release public key file could not be opened safely"
            ) from error
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
            ):
                raise ModelReleaseKeyConfigurationError(
                    "model release public key file changed while being opened"
                )
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                public_key_pem = handle.read(_MAX_PUBLIC_KEY_BYTES + 1)
        finally:
            os.close(descriptor)
        return cls.from_pem_bytes(
            public_key_pem=public_key_pem,
            expected_key_id=expected_key_id,
        )

    def verify(self, value: SignedLLMReleaseManifest) -> bool:
        if value.signing_key_id != self._expected_key_id:
            return False
        try:
            self._public_key.verify(
                value.signature_bytes,
                value.manifest.canonical_bytes(),
            )
        except InvalidSignature:
            return False
        return True


__all__ = [
    "Ed25519ModelReleaseSignatureVerifier",
    "ModelReleaseKeyConfigurationError",
]
