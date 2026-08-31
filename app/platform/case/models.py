"""Technology-neutral Case aggregate and workflow values."""

import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.errors import ValidationError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

MAX_ATTRIBUTES_BYTES = 64 * 1024
MAX_ATTRIBUTES_DEPTH = 8
MAX_ATTRIBUTES_KEYS = 256
MAX_ATTRIBUTE_KEY_LENGTH = 128


class CaseStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    INVALID_INPUT = "INVALID_INPUT"
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    RETRY_WAITING = "RETRY_WAITING"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    APPROVAL_CANDIDATE = "APPROVAL_CANDIDATE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    ADDITIONAL_EVIDENCE_REQUIRED = "ADDITIONAL_EVIDENCE_REQUIRED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class DomainType(StrEnum):
    PRODUCT_DEFECT_CS = "product_defect_cs"


class RequestedAction(StrEnum):
    EXCHANGE = "EXCHANGE"
    REFUND = "REFUND"
    RETURN = "RETURN"
    REPAIR = "REPAIR"
    INFORMATION = "INFORMATION"
    OTHER = "OTHER"
    UNSPECIFIED = "UNSPECIFIED"


class CaseSourceScope(StrEnum):
    """Trusted provenance boundary for operational metrics and learning assets."""

    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    SHADOW = "SHADOW"
    IMPORTED = "IMPORTED"
    PILOT_LIVE = "PILOT_LIVE"
    NOT_ATTESTED = "NOT_ATTESTED"


def _validate_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(UTC)


def validate_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Reject unsafe or operationally unbounded Case attribute payloads.

    Case attributes remain extensible for versioned domain snapshots, but they
    are not an unbounded document store.  Limits are deliberately enforced in
    the technology-neutral boundary so HTTP, seeds, and background imports all
    receive the same protection.
    """

    key_count = 0

    def validate(item: JsonValue, *, depth: int) -> None:
        nonlocal key_count
        if depth > MAX_ATTRIBUTES_DEPTH:
            raise ValueError(f"attributes must not exceed {MAX_ATTRIBUTES_DEPTH} levels")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        if isinstance(item, list):
            for nested in item:
                validate(nested, depth=depth + 1)
        elif isinstance(item, dict):
            key_count += len(item)
            if key_count > MAX_ATTRIBUTES_KEYS:
                raise ValueError(f"attributes must not exceed {MAX_ATTRIBUTES_KEYS} keys")
            for key, nested in item.items():
                if not key.strip():
                    raise ValueError("attribute keys must not be blank")
                if len(key) > MAX_ATTRIBUTE_KEY_LENGTH:
                    raise ValueError(
                        f"attribute keys must not exceed {MAX_ATTRIBUTE_KEY_LENGTH} characters"
                    )
                validate(nested, depth=depth + 1)

    validate(value, depth=1)
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exception:
        raise ValueError("attributes must be a JSON-compatible object") from exception
    if len(encoded) > MAX_ATTRIBUTES_BYTES:
        raise ValueError(f"attributes must not exceed {MAX_ATTRIBUTES_BYTES} UTF-8 bytes")
    if "synthetic_commerce_context" in value:
        from app.platform.commerce_context import validate_synthetic_commerce_context

        validate_synthetic_commerce_context(value["synthetic_commerce_context"])
    return value


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    domain_type: DomainType = DomainType.PRODUCT_DEFECT_CS
    status: CaseStatus = CaseStatus.RECEIVED
    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=1, max_length=20_000)
    requested_action: RequestedAction = RequestedAction.UNSPECIFIED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    source_scope: CaseSourceScope = CaseSourceScope.NOT_ATTESTED
    source_provenance: str = Field(default="unattested/manual", min_length=1, max_length=255)
    created_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("customer_message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("customer_message must not be blank")
        return normalized

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @field_validator("attributes")
    @classmethod
    def require_json_attributes(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return validate_json_object(value)

    @classmethod
    def create(
        cls,
        *,
        case_id: str,
        tenant_id: str,
        order_ref: str,
        product_ref: str,
        customer_message: str,
        requested_action: RequestedAction,
        attributes: dict[str, JsonValue],
        created_by: str,
        now: datetime,
        source_scope: CaseSourceScope | None = None,
        source_provenance: str | None = None,
    ) -> Self:
        inferred_scope = source_scope
        inferred_provenance = source_provenance
        if inferred_scope is None:
            if "synthetic_commerce_context" in attributes:
                inferred_scope = CaseSourceScope.SYNTHETIC_DEMO
                inferred_provenance = inferred_provenance or "synthetic_commerce_context/1.0.0"
            else:
                inferred_scope = CaseSourceScope.NOT_ATTESTED
                inferred_provenance = inferred_provenance or "unattested/manual"
        resolved_scope = inferred_scope or CaseSourceScope.NOT_ATTESTED
        resolved_provenance = inferred_provenance or f"trusted/{resolved_scope.value.lower()}"
        return cls(
            id=case_id,
            tenant_id=tenant_id,
            order_ref=order_ref,
            product_ref=product_ref,
            customer_message=customer_message,
            requested_action=requested_action,
            attributes=attributes,
            source_scope=resolved_scope,
            source_provenance=resolved_provenance,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )


class CaseStatusTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    from_status: CaseStatus | None = None
    to_status: CaseStatus
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        return _validate_utc(value)

    @classmethod
    def initial(
        cls,
        *,
        transition_id: str,
        case: Case,
        now: datetime,
    ) -> Self:
        if case.status is not CaseStatus.RECEIVED:
            raise ValidationError("A newly created case must start in RECEIVED.")
        return cls(
            id=transition_id,
            tenant_id=case.tenant_id,
            case_id=case.id,
            from_status=None,
            to_status=CaseStatus.RECEIVED,
            actor_id=case.created_by,
            reason="case_created",
            occurred_at=now,
        )


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    operation: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=255)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1)
    response_status: int = Field(ge=100, le=599)
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        return _validate_utc(value)
