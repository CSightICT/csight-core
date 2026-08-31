"""Technology-neutral human review workflow and final-decision contract."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.errors import CSightError
from app.platform.policy_engine import EvaluationSummary, PolicyEffect, PolicyEffectType
from app.platform.tenant import Role

TASK_MAPPING_NAME = "review_task_mapping"
TASK_MAPPING_VERSION = "1.0.0"
PACKET_SCHEMA_VERSION = "1.0.0"
DECISION_SCHEMA_VERSION = "1.0.0"
OUTCOME_RELATION_RULE_VERSION = "1.0.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReviewTaskType(StrEnum):
    STANDARD_REVIEW = "STANDARD_REVIEW"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    MANAGER_REVIEW = "MANAGER_REVIEW"
    POLICY_EXCEPTION_REVIEW = "POLICY_EXCEPTION_REVIEW"
    SAFETY_REVIEW = "SAFETY_REVIEW"


class ReviewPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReviewTaskStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class ReviewActionType(StrEnum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    CLAIMED = "CLAIMED"
    RELEASED = "RELEASED"
    EVIDENCE_REQUESTED = "EVIDENCE_REQUESTED"
    RESUMED = "RESUMED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class AssignmentType(StrEnum):
    SELF_CLAIM = "SELF_CLAIM"
    ADMIN_ASSIGNMENT = "ADMIN_ASSIGNMENT"
    ESCALATION_CLAIM = "ESCALATION_CLAIM"
    WAITING_OWNER_RECOVERY = "WAITING_OWNER_RECOVERY"
    CASE_ASSIGNMENT_INHERITANCE = "CASE_ASSIGNMENT_INHERITANCE"


class AdditionalEvidenceReason(StrEnum):
    IMAGE_REQUIRED = "IMAGE_REQUIRED"
    DEFECT_AREA_NOT_VISIBLE = "DEFECT_AREA_NOT_VISIBLE"
    IMAGE_TOO_DARK = "IMAGE_TOO_DARK"
    IMAGE_BLURRED = "IMAGE_BLURRED"
    PRODUCT_NOT_VISIBLE = "PRODUCT_NOT_VISIBLE"
    ORDER_REFERENCE_REQUIRED = "ORDER_REFERENCE_REQUIRED"
    PRODUCT_REFERENCE_REQUIRED = "PRODUCT_REFERENCE_REQUIRED"
    DESCRIPTION_INSUFFICIENT = "DESCRIPTION_INSUFFICIENT"
    OTHER = "OTHER"


class EscalationReason(StrEnum):
    HIGH_VALUE_CASE = "HIGH_VALUE_CASE"
    POLICY_EXCEPTION = "POLICY_EXCEPTION"
    CONFLICTING_POLICY = "CONFLICTING_POLICY"
    SAFETY_RISK = "SAFETY_RISK"
    LEGAL_RISK = "LEGAL_RISK"
    REPEAT_CLAIM = "REPEAT_CLAIM"
    INSUFFICIENT_AUTHORITY = "INSUFFICIENT_AUTHORITY"
    OTHER = "OTHER"


class HumanDecisionType(StrEnum):
    APPROVE_REFUND = "APPROVE_REFUND"
    APPROVE_EXCHANGE = "APPROVE_EXCHANGE"
    APPROVE_RESHIPMENT = "APPROVE_RESHIPMENT"
    APPROVE_REPAIR = "APPROVE_REPAIR"
    REJECT_REQUEST = "REJECT_REQUEST"
    PROVIDE_INFORMATION = "PROVIDE_INFORMATION"
    NO_ACTION = "NO_ACTION"


class DecisionReason(StrEnum):
    POLICY_CONDITION_MET = "POLICY_CONDITION_MET"
    POLICY_CONDITION_NOT_MET = "POLICY_CONDITION_NOT_MET"
    POLICY_EXCEPTION = "POLICY_EXCEPTION"
    EVIDENCE_SUFFICIENT = "EVIDENCE_SUFFICIENT"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    CUSTOMER_INFORMATION_ONLY = "CUSTOMER_INFORMATION_ONLY"
    OTHER = "OTHER"


class DecisionBasisType(StrEnum):
    POLICY_RULE_RESULT = "POLICY_RULE_RESULT"
    POLICY_CITATION = "POLICY_CITATION"
    CASE_EVIDENCE = "CASE_EVIDENCE"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"


class OutcomeRelation(StrEnum):
    CONSISTENT_WITH_RECOMMENDATION = "CONSISTENT_WITH_RECOMMENDATION"
    DIFFERS_FROM_RECOMMENDATION = "DIFFERS_FROM_RECOMMENDATION"
    NO_COMPARABLE_RECOMMENDATION = "NO_COMPARABLE_RECOMMENDATION"
    INDETERMINATE_POLICY = "INDETERMINATE_POLICY"


class ReviewTaskNotFoundError(CSightError):
    code = "REVIEW_TASK_NOT_FOUND"
    default_message = "The requested human review task was not found."


class ReviewTaskVersionConflictError(CSightError):
    code = "REVIEW_TASK_VERSION_CONFLICT"
    default_message = "The human review task version is stale."


class ReviewTaskAlreadyClaimedError(CSightError):
    code = "REVIEW_TASK_ALREADY_CLAIMED"
    default_message = "The human review task is already claimed."


class InvalidReviewTransitionError(CSightError):
    code = "INVALID_REVIEW_TRANSITION"
    default_message = "The requested human review state transition is not allowed."


class InvalidDecisionBasisError(CSightError):
    code = "INVALID_DECISION_BASIS"
    default_message = "The final decision basis is outside the immutable review packet."


class DuplicateHumanDecisionError(CSightError):
    code = "DUPLICATE_HUMAN_DECISION"
    default_message = "A final human decision already exists for this review task."


class ReviewPacketIntegrityError(CSightError):
    code = "REVIEW_PACKET_INTEGRITY_FAILED"
    default_message = "The immutable review packet failed integrity validation."


class DecisionBasisReference(_Strict):
    type: DecisionBasisType
    reference_id: str = Field(min_length=1, max_length=320)


class HumanDecisionRequest(_Strict):
    decision: HumanDecisionType
    reason_codes: tuple[DecisionReason, ...] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=10, max_length=2000)
    basis: tuple[DecisionBasisReference, ...] = Field(min_length=1, max_length=30)

    @field_validator("rationale")
    @classmethod
    def rationale_not_blank(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("rationale must contain at least 10 non-whitespace characters")
        return value.strip()

    @field_validator("basis")
    @classmethod
    def policy_basis_required(
        cls, value: tuple[DecisionBasisReference, ...]
    ) -> tuple[DecisionBasisReference, ...]:
        if not any(
            item.type in {DecisionBasisType.POLICY_RULE_RESULT, DecisionBasisType.POLICY_CITATION}
            for item in value
        ):
            raise ValueError("a policy rule result or policy citation basis is required")
        return value


class ReviewTask(_Strict):
    id: str
    tenant_id: str
    case_id: str
    policy_evaluation_run_id: str
    task_type: ReviewTaskType
    priority: ReviewPriority
    status: ReviewTaskStatus
    current_assignee_id: str | None
    version: int = Field(ge=1)
    mapping_rule_name: Literal["review_task_mapping"] = TASK_MAPPING_NAME
    mapping_rule_version: Literal["1.0.0"] = TASK_MAPPING_VERSION
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class ReviewAssignee(_Strict):
    user_id: str
    display_name: str
    email: str
    roles: tuple[Role, ...]


class ReviewPacket(_Strict):
    id: str
    tenant_id: str
    review_task_id: str
    case_id: str
    analysis_run_id: str
    policy_evaluation_run_id: str
    rule_set_id: str
    rule_set_version: str
    rule_set_hash: str
    llm_extraction_result_v2_id: str
    completeness_result_id: str
    vision_result_ids: tuple[str, ...] = ()
    alignment_result_id: str | None = None
    citation_pack_id: str | None = None
    grounding_result_id: str | None = None
    case_metadata_snapshot: dict[str, object]
    qualification_snapshot: dict[str, object]
    policy_effects: tuple[PolicyEffect, ...]
    policy_summary_status: EvaluationSummary
    packet_schema_version: Literal["1.0.0"] = PACKET_SCHEMA_VERSION
    packet_hash: str
    created_at: datetime


class ReviewAction(_Strict):
    id: str
    tenant_id: str
    review_task_id: str
    action_type: ReviewActionType
    from_status: ReviewTaskStatus | None
    to_status: ReviewTaskStatus
    actor_id: str | None
    actor_role: Role | None
    reason_codes: tuple[str, ...] = ()
    rationale: str | None = None
    action_payload: dict[str, object] = Field(default_factory=dict)
    expected_task_version: int
    resulting_task_version: int
    created_at: datetime


class HumanDecision(_Strict):
    id: str
    tenant_id: str
    review_task_id: str
    decision_type: HumanDecisionType
    reason_codes: tuple[DecisionReason, ...]
    rationale: str
    basis: tuple[DecisionBasisReference, ...]
    outcome_relation: OutcomeRelation
    outcome_relation_rule_version: Literal["1.0.0"] = OUTCOME_RELATION_RULE_VERSION
    decided_by: str
    decided_at: datetime
    decision_schema_version: Literal["1.0.0"] = DECISION_SCHEMA_VERSION
    content_hash: str


_TASK_PRECEDENCE: tuple[ReviewTaskType, ...] = (
    ReviewTaskType.SAFETY_REVIEW,
    ReviewTaskType.MANAGER_REVIEW,
    ReviewTaskType.POLICY_EXCEPTION_REVIEW,
    ReviewTaskType.EVIDENCE_REVIEW,
    ReviewTaskType.STANDARD_REVIEW,
)
_PRIORITY = {
    ReviewTaskType.STANDARD_REVIEW: ReviewPriority.NORMAL,
    ReviewTaskType.EVIDENCE_REVIEW: ReviewPriority.NORMAL,
    ReviewTaskType.MANAGER_REVIEW: ReviewPriority.HIGH,
    ReviewTaskType.POLICY_EXCEPTION_REVIEW: ReviewPriority.HIGH,
    ReviewTaskType.SAFETY_REVIEW: ReviewPriority.CRITICAL,
}
_EFFECT_TASK = {
    PolicyEffectType.REQUIRE_HUMAN_REVIEW: ReviewTaskType.STANDARD_REVIEW,
    PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE: ReviewTaskType.EVIDENCE_REVIEW,
    PolicyEffectType.REQUIRE_MANAGER_REVIEW: ReviewTaskType.MANAGER_REVIEW,
    PolicyEffectType.FLAG_POLICY_EXCEPTION: ReviewTaskType.POLICY_EXCEPTION_REVIEW,
    PolicyEffectType.PROHIBIT_AUTOMATION: ReviewTaskType.STANDARD_REVIEW,
}
_TRANSITIONS = {
    (ReviewTaskStatus.PENDING, ReviewActionType.CLAIMED): ReviewTaskStatus.CLAIMED,
    (ReviewTaskStatus.CLAIMED, ReviewActionType.RELEASED): ReviewTaskStatus.PENDING,
    (
        ReviewTaskStatus.CLAIMED,
        ReviewActionType.EVIDENCE_REQUESTED,
    ): ReviewTaskStatus.WAITING_FOR_EVIDENCE,
    (ReviewTaskStatus.WAITING_FOR_EVIDENCE, ReviewActionType.RESUMED): ReviewTaskStatus.CLAIMED,
    (ReviewTaskStatus.CLAIMED, ReviewActionType.ESCALATED): ReviewTaskStatus.ESCALATED,
    (ReviewTaskStatus.ESCALATED, ReviewActionType.CLAIMED): ReviewTaskStatus.CLAIMED,
    (ReviewTaskStatus.CLAIMED, ReviewActionType.RESOLVED): ReviewTaskStatus.RESOLVED,
}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def map_policy_effects(effects: tuple[PolicyEffect, ...]) -> tuple[ReviewTaskType, ReviewPriority]:
    candidates = {_EFFECT_TASK[item.type] for item in effects if item.type in _EFFECT_TASK}
    if not candidates:
        raise ReviewPacketIntegrityError("Policy evaluation has no review-producing effect.")
    task_type = next(item for item in _TASK_PRECEDENCE if item in candidates)
    return task_type, _PRIORITY[task_type]


def transition(status: ReviewTaskStatus, action: ReviewActionType) -> ReviewTaskStatus:
    try:
        return _TRANSITIONS[(status, action)]
    except KeyError as error:
        raise InvalidReviewTransitionError() from error


def can_claim(task_type: ReviewTaskType, status: ReviewTaskStatus, roles: frozenset[Role]) -> bool:
    if Role.ADMIN in roles:
        return status in {ReviewTaskStatus.PENDING, ReviewTaskStatus.ESCALATED}
    return (
        Role.REVIEWER in roles
        and status is ReviewTaskStatus.PENDING
        and task_type
        in {
            ReviewTaskType.STANDARD_REVIEW,
            ReviewTaskType.EVIDENCE_REVIEW,
            ReviewTaskType.POLICY_EXCEPTION_REVIEW,
        }
    )


def actor_role(roles: frozenset[Role]) -> Role:
    if Role.ADMIN in roles:
        return Role.ADMIN
    if Role.REVIEWER in roles:
        return Role.REVIEWER
    raise InvalidReviewTransitionError("A reviewer or administrator is required.")


def compute_outcome_relation(
    *,
    summary: EvaluationSummary,
    effects: tuple[PolicyEffect, ...],
    decision: HumanDecisionType,
) -> OutcomeRelation:
    if summary is EvaluationSummary.BLOCKED_INPUT_INCOMPLETE:
        return OutcomeRelation.INDETERMINATE_POLICY
    eligible = {
        item.value
        for item in effects
        if item.type is PolicyEffectType.MARK_REVIEW_ELIGIBILITY and item.value is not None
    }
    expected = {
        "RETURN_REVIEW": HumanDecisionType.APPROVE_REFUND,
        "ACTION_REVIEW": None,
        "EXCHANGE_REVIEW": HumanDecisionType.APPROVE_EXCHANGE,
        "REFUND_REVIEW": HumanDecisionType.APPROVE_REFUND,
        "REPAIR_REVIEW": HumanDecisionType.APPROVE_REPAIR,
        "RESHIPMENT_REVIEW": HumanDecisionType.APPROVE_RESHIPMENT,
    }
    comparable = {
        expected[item] for item in eligible if item in expected and expected[item] is not None
    }
    if comparable:
        return (
            OutcomeRelation.CONSISTENT_WITH_RECOMMENDATION
            if decision in comparable
            else OutcomeRelation.DIFFERS_FROM_RECOMMENDATION
        )
    if any(
        item.type is PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE for item in effects
    ) and decision in {
        HumanDecisionType.APPROVE_REFUND,
        HumanDecisionType.APPROVE_EXCHANGE,
        HumanDecisionType.APPROVE_RESHIPMENT,
        HumanDecisionType.APPROVE_REPAIR,
    }:
        return OutcomeRelation.DIFFERS_FROM_RECOMMENDATION
    return OutcomeRelation.NO_COMPARABLE_RECOMMENDATION
