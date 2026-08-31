"""Public contract for generic signed Case intake."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.cases import CreateCaseResult
from app.platform.case import (
    CaseSourceScope,
    CaseStatus,
    JsonValue,
    RequestedAction,
    validate_json_object,
)

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SignedIntakeCaseRequest(BaseModel):
    """Tenant-free source payload; deployment configuration owns all trust scope."""

    model_config = _MODEL_CONFIG

    schema_version: Literal["signed_case_intake/1.0.0"]
    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=1, max_length=20_000, repr=False)
    requested_action: RequestedAction = RequestedAction.UNSPECIFIED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("customer_message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("customer_message must not be blank")
        return normalized

    @field_validator("attributes")
    @classmethod
    def require_json_attributes(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return validate_json_object(value)


class SignedIntakeCaseResponse(BaseModel):
    model_config = _MODEL_CONFIG

    source_event_id: str
    case_id: str
    status: CaseStatus
    source_scope: Literal[CaseSourceScope.PILOT_LIVE]
    created_at: datetime
    replayed: bool

    @classmethod
    def from_result(cls, *, source_event_id: str, result: CreateCaseResult) -> Self:
        return cls(
            source_event_id=source_event_id,
            case_id=result.case.id,
            status=result.case.status,
            source_scope=CaseSourceScope.PILOT_LIVE,
            created_at=result.case.created_at,
            replayed=result.replayed,
        )


__all__ = ["SignedIntakeCaseRequest", "SignedIntakeCaseResponse"]
