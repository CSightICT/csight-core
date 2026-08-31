"""Framework-free contracts for tenant-bound signed Case intake."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.errors import CSightError

SIGNED_INTAKE_CONTEXT = "csight-signed-case-intake/1.0.0"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SignedIntakeSource(_Contract):
    """Deployment-authorized source bound to exactly one tenant and actor."""

    key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    tenant_id: str = Field(min_length=1, max_length=64)
    actor_user_id: str = Field(min_length=1, max_length=64)
    provenance: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,191}$")


class SignedIntakeProof(_Contract):
    """Headers and raw-body digest covered by an Ed25519 signature."""

    method: str = Field(pattern=r"^[A-Z]+$", max_length=16)
    path: str = Field(pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+$", max_length=2048)
    key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    event_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    timestamp: int = Field(ge=0, le=9_999_999_999)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_base64: str = Field(min_length=88, max_length=88, repr=False)

    @field_validator("signature_base64")
    @classmethod
    def require_ed25519_signature(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("signature must be valid base64") from None
        if len(decoded) != 64:
            raise ValueError("Ed25519 signature must contain exactly 64 bytes")
        return value

    @property
    def signature_bytes(self) -> bytes:
        return base64.b64decode(self.signature_base64, validate=True)

    def canonical_bytes(self) -> bytes:
        return "\n".join(
            (
                SIGNED_INTAKE_CONTEXT,
                self.method,
                self.path,
                self.key_id,
                self.event_id,
                str(self.timestamp),
                self.body_sha256,
            )
        ).encode("utf-8")


class AuthenticatedSignedIntake(_Contract):
    source: SignedIntakeSource
    authenticated_at: datetime

    @field_validator("authenticated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authenticated_at must be timezone-aware")
        return value.astimezone(UTC)


class SignedIntakeAuthenticationError(CSightError):
    code = "SIGNED_INTAKE_AUTHENTICATION_FAILED"
    default_message = "The signed intake request could not be authenticated."
    retryable: ClassVar[bool] = False


__all__ = [
    "SIGNED_INTAKE_CONTEXT",
    "AuthenticatedSignedIntake",
    "SignedIntakeAuthenticationError",
    "SignedIntakeProof",
    "SignedIntakeSource",
]
