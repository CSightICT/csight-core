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


def _validate_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(UTC)


def validate_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Reject values that JSON cannot represent deterministically."""

    def validate(item: JsonValue) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        if isinstance(item, list):
            for nested in item:
                validate(nested)
        elif isinstance(item, dict):
            for nested in item.values():
                validate(nested)

    validate(value)
    try:
        json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exception:
        raise ValueError("attributes must be a JSON-compatible object") from exception
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
    ) -> Self:
        return cls(
            id=case_id,
            tenant_id=tenant_id,
            order_ref=order_ref,
            product_ref=product_ref,
            customer_message=customer_message,
            requested_action=requested_action,
            attributes=attributes,
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
