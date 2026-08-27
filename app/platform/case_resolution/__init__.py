"""Technology-neutral Case Resolution and external-action simulation contract."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.platform.errors import CSightError
from app.platform.human_review import HumanDecisionType

ACTION_MAPPING_NAME = "human_decision_to_external_action"
ACTION_MAPPING_VERSION = "1.0.0"
RESOLUTION_SCHEMA_VERSION = "1.0.0"
ACTION_INTENT_SCHEMA_VERSION = "1.0.0"
SIMULATION_RESULT_SCHEMA_VERSION = "1.0.0"
CASE_RESOLUTION_REQUESTED_EVENT = "case_resolution.requested.v1"
EXTERNAL_ACTION_SIMULATION_REQUESTED_EVENT = "external_action.simulation_requested.v1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ResolutionStatus(StrEnum):
    DECISION_RECORDED = "DECISION_RECORDED"
    ACTION_NOT_REQUIRED = "ACTION_NOT_REQUIRED"
    MANUAL_FOLLOW_UP_REQUIRED = "MANUAL_FOLLOW_UP_REQUIRED"
    ACTION_NEEDS_INPUT = "ACTION_NEEDS_INPUT"
    ACTION_READY = "ACTION_READY"
    ACTION_DRY_RUN_PENDING = "ACTION_DRY_RUN_PENDING"
    ACTION_DRY_RUN_VALIDATED = "ACTION_DRY_RUN_VALIDATED"
    ACTION_DRY_RUN_FAILED = "ACTION_DRY_RUN_FAILED"


class ResolutionEventType(StrEnum):
    DECISION_RECORDED = "DECISION_RECORDED"
    ACTION_NOT_REQUIRED = "ACTION_NOT_REQUIRED"
    MANUAL_FOLLOW_UP_REQUIRED = "MANUAL_FOLLOW_UP_REQUIRED"
    ACTION_NEEDS_INPUT = "ACTION_NEEDS_INPUT"
    ACTION_READY = "ACTION_READY"
    ACTION_DRY_RUN_PENDING = "ACTION_DRY_RUN_PENDING"
    ACTION_DRY_RUN_VALIDATED = "ACTION_DRY_RUN_VALIDATED"
    ACTION_DRY_RUN_FAILED = "ACTION_DRY_RUN_FAILED"


class ExternalActionType(StrEnum):
    REFUND = "REFUND"
    EXCHANGE = "EXCHANGE"
    RESHIPMENT = "RESHIPMENT"
    REPAIR = "REPAIR"


class ExternalActionMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


class SimulationAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SimulationOutcome(StrEnum):
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


class CaseResolutionNotFoundError(CSightError):
    code = "CASE_RESOLUTION_NOT_FOUND"
    default_message = "The requested Case Resolution was not found."


class ExternalActionIntentNotFoundError(CSightError):
    code = "EXTERNAL_ACTION_INTENT_NOT_FOUND"
    default_message = "The requested external Action Intent was not found."


class CaseResolutionIntegrityError(CSightError):
    code = "CASE_RESOLUTION_INTEGRITY_FAILED"
    default_message = "The immutable Case Resolution data failed integrity validation."


class ExternalActionSimulationError(CSightError):
    code = "EXTERNAL_ACTION_SIMULATION_FAILED"
    default_message = "The external Action Intent simulation failed."


class CaseResolution(_Strict):
    id: str
    tenant_id: str
    case_id: str
    source_review_task_id: str
    source_human_decision_id: str
    status: ResolutionStatus
    version: int = Field(ge=1)
    mapping_name: Literal["human_decision_to_external_action"] = ACTION_MAPPING_NAME
    mapping_version: Literal["1.0.0"] = ACTION_MAPPING_VERSION
    resolution_schema_version: Literal["1.0.0"] = RESOLUTION_SCHEMA_VERSION
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    failure_code: str | None = None
    failure_message: str | None = None
    correlation_id: str
    created_at: datetime
    updated_at: datetime


class CaseResolutionEvent(_Strict):
    id: str
    tenant_id: str
    case_id: str
    resolution_id: str
    sequence: int = Field(ge=1)
    event_type: ResolutionEventType
    from_status: ResolutionStatus | None
    to_status: ResolutionStatus
    human_decision_id: str | None = None
    external_action_intent_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ExternalActionIntent(_Strict):
    id: str
    tenant_id: str
    case_id: str
    resolution_id: str
    human_decision_id: str
    action_type: ExternalActionType
    mode: Literal["DRY_RUN"] = "DRY_RUN"
    order_ref: str
    product_ref: str | None = None
    amount: str | None = None
    currency: str | None = None
    quantity: int | None = None
    shipping_address_ref: str | None = None
    mapping_name: Literal["human_decision_to_external_action"] = ACTION_MAPPING_NAME
    mapping_version: Literal["1.0.0"] = ACTION_MAPPING_VERSION
    intent_schema_version: Literal["1.0.0"] = ACTION_INTENT_SCHEMA_VERSION
    content_hash: str
    created_at: datetime


class ExternalActionSimulationAttempt(_Strict):
    id: str
    tenant_id: str
    case_id: str
    resolution_id: str
    external_action_intent_id: str
    attempt_number: int = Field(ge=1)
    execution_token: str
    status: SimulationAttemptStatus
    mode: ExternalActionMode
    started_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class ExternalActionSimulationResult(_Strict):
    id: str
    tenant_id: str
    case_id: str
    resolution_id: str
    external_action_intent_id: str
    simulation_attempt_id: str
    outcome: SimulationOutcome
    mode: ExternalActionMode
    side_effects_performed: Literal[False] = False
    failure_code: str | None = None
    failure_message: str | None = None
    simulated_request: dict[str, object]
    simulated_response: dict[str, object]
    result_schema_version: Literal["1.0.0"] = SIMULATION_RESULT_SCHEMA_VERSION
    content_hash: str
    created_at: datetime


class ExternalActionIntentDetail(_Strict):
    intent: ExternalActionIntent
    attempts: tuple[ExternalActionSimulationAttempt, ...] = ()
    results: tuple[ExternalActionSimulationResult, ...] = ()


class ActionInputAssessment(_Strict):
    action_type: ExternalActionType | None
    terminal_status: ResolutionStatus | None
    values: dict[str, object] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()


class SimulationClaim(_Strict):
    event_id: str
    tenant_id: str
    case_id: str
    resolution_id: str
    intent: ExternalActionIntent
    attempt_id: str
    execution_token: str
    correlation_id: str


class SimulationAdapterResult(_Strict):
    outcome: SimulationOutcome
    mode: ExternalActionMode
    side_effects_performed: Literal[False] = False
    failure_code: str | None = None
    failure_message: str | None = None
    simulated_request: dict[str, object]
    simulated_response: dict[str, object]


_DECISION_ACTION: dict[HumanDecisionType, ExternalActionType] = {
    HumanDecisionType.APPROVE_REFUND: ExternalActionType.REFUND,
    HumanDecisionType.APPROVE_EXCHANGE: ExternalActionType.EXCHANGE,
    HumanDecisionType.APPROVE_RESHIPMENT: ExternalActionType.RESHIPMENT,
    HumanDecisionType.APPROVE_REPAIR: ExternalActionType.REPAIR,
}
_NO_ACTION_DECISIONS = {
    HumanDecisionType.REJECT_REQUEST,
    HumanDecisionType.NO_ACTION,
}
_ALLOWED_INPUT_FIELDS = frozenset({"amount", "currency", "quantity", "shipping_address_ref"})
_REQUIRED_FIELDS: dict[ExternalActionType, tuple[str, ...]] = {
    ExternalActionType.REFUND: ("order_ref", "amount", "currency"),
    ExternalActionType.EXCHANGE: (
        "order_ref",
        "product_ref",
        "quantity",
        "shipping_address_ref",
    ),
    ExternalActionType.RESHIPMENT: (
        "order_ref",
        "product_ref",
        "quantity",
        "shipping_address_ref",
    ),
    ExternalActionType.REPAIR: ("order_ref", "product_ref", "quantity"),
}
_ACTION_INPUT_FIELDS: dict[ExternalActionType, frozenset[str]] = {
    ExternalActionType.REFUND: frozenset({"amount", "currency"}),
    ExternalActionType.EXCHANGE: frozenset({"quantity", "shipping_address_ref"}),
    ExternalActionType.RESHIPMENT: frozenset({"quantity", "shipping_address_ref"}),
    ExternalActionType.REPAIR: frozenset({"quantity"}),
}
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_FIXED_POINT_AMOUNT = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assess_action_input(
    *,
    decision: HumanDecisionType,
    order_ref: object,
    product_ref: object,
    attributes: object,
) -> ActionInputAssessment:
    """Map one human decision without deriving or defaulting any Action input."""

    if decision in _NO_ACTION_DECISIONS:
        return ActionInputAssessment(
            action_type=None,
            terminal_status=ResolutionStatus.ACTION_NOT_REQUIRED,
        )
    if decision is HumanDecisionType.PROVIDE_INFORMATION:
        return ActionInputAssessment(
            action_type=None,
            terminal_status=ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
        )

    action_type = _DECISION_ACTION[decision]
    missing: list[str] = []
    invalid: list[str] = []
    values: dict[str, object] = {}

    _validate_reference("order_ref", order_ref, values, missing, invalid)
    if "product_ref" in _REQUIRED_FIELDS[action_type]:
        _validate_reference("product_ref", product_ref, values, missing, invalid)

    external_input: object = None
    if isinstance(attributes, dict):
        external_input = attributes.get("external_action_input")
    if external_input is None:
        external_input = {}
    if not isinstance(external_input, dict):
        invalid.append("external_action_input")
        external_input = {}

    provided_fields = set(external_input)
    unknown = provided_fields - _ALLOWED_INPUT_FIELDS
    irrelevant = provided_fields - _ACTION_INPUT_FIELDS[action_type] - unknown
    invalid.extend(f"external_action_input.{name}" for name in sorted(unknown | irrelevant))

    for name in sorted(_ACTION_INPUT_FIELDS[action_type]):
        if name not in external_input:
            missing.append(name)
            continue
        value = external_input[name]
        normalized = _normalize_input(name, value)
        if normalized is None:
            invalid.append(name)
        else:
            values[name] = normalized

    return ActionInputAssessment(
        action_type=action_type,
        terminal_status=(ResolutionStatus.ACTION_NEEDS_INPUT if missing or invalid else None),
        values=values,
        missing_fields=tuple(sorted(set(missing))),
        invalid_fields=tuple(sorted(set(invalid))),
    )


def action_intent_hash_payload(intent: ExternalActionIntent) -> dict[str, object]:
    return {
        "id": intent.id,
        "tenant_id": intent.tenant_id,
        "case_id": intent.case_id,
        "resolution_id": intent.resolution_id,
        "human_decision_id": intent.human_decision_id,
        "action_type": intent.action_type.value,
        "mode": intent.mode,
        "order_ref": intent.order_ref,
        "product_ref": intent.product_ref,
        "amount": intent.amount,
        "currency": intent.currency,
        "quantity": intent.quantity,
        "shipping_address_ref": intent.shipping_address_ref,
        "mapping_name": intent.mapping_name,
        "mapping_version": intent.mapping_version,
        "intent_schema_version": intent.intent_schema_version,
        "created_at": intent.created_at.isoformat(),
    }


def _validate_reference(
    name: str,
    value: object,
    values: dict[str, object],
    missing: list[str],
    invalid: list[str],
) -> None:
    if value is None:
        missing.append(name)
    elif not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        invalid.append(name)
    else:
        values[name] = value.strip()


def _normalize_input(name: str, value: object) -> object | None:
    if name == "amount":
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or _FIXED_POINT_AMOUNT.fullmatch(value) is None
        ):
            return None
        try:
            amount = Decimal(value)
        except InvalidOperation:
            return None
        if not amount.is_finite() or amount <= 0:
            return None
        sign, digits, exponent = amount.as_tuple()
        del sign
        if not isinstance(exponent, int):
            return None
        scale = max(0, -exponent)
        integer_digits = max(1, len(digits) + exponent)
        if scale > 4 or integer_digits > 15 or len(digits) > 19:
            return None
        return format(amount, "f")
    if name == "currency":
        return value if isinstance(value, str) and _CURRENCY.fullmatch(value) else None
    if name == "quantity":
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 1000
            else None
        )
    if name == "shipping_address_ref":
        return (
            value.strip()
            if isinstance(value, str) and value.strip() and len(value.strip()) <= 255
            else None
        )
    return None


__all__ = [
    "ACTION_INTENT_SCHEMA_VERSION",
    "ACTION_MAPPING_NAME",
    "ACTION_MAPPING_VERSION",
    "CASE_RESOLUTION_REQUESTED_EVENT",
    "EXTERNAL_ACTION_SIMULATION_REQUESTED_EVENT",
    "RESOLUTION_SCHEMA_VERSION",
    "SIMULATION_RESULT_SCHEMA_VERSION",
    "ActionInputAssessment",
    "CaseResolution",
    "CaseResolutionEvent",
    "CaseResolutionIntegrityError",
    "CaseResolutionNotFoundError",
    "ExternalActionIntent",
    "ExternalActionIntentDetail",
    "ExternalActionIntentNotFoundError",
    "ExternalActionMode",
    "ExternalActionSimulationAttempt",
    "ExternalActionSimulationError",
    "ExternalActionSimulationResult",
    "ExternalActionType",
    "ResolutionEventType",
    "ResolutionStatus",
    "SimulationAdapterResult",
    "SimulationAttemptStatus",
    "SimulationClaim",
    "SimulationOutcome",
    "action_intent_hash_payload",
    "assess_action_input",
    "canonical_hash",
]
