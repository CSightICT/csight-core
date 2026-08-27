"""Pure human-review mapping, workflow, authorization, and decision contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.application.human_review import RequestEvidenceCommand
from app.platform.errors import ForbiddenError
from app.platform.human_review import (
    AdditionalEvidenceReason,
    DecisionBasisReference,
    DecisionBasisType,
    DecisionReason,
    HumanDecisionRequest,
    HumanDecisionType,
    InvalidReviewTransitionError,
    OutcomeRelation,
    ReviewActionType,
    ReviewPriority,
    ReviewTaskStatus,
    ReviewTaskType,
    can_claim,
    canonical_hash,
    compute_outcome_relation,
    map_policy_effects,
    transition,
)
from app.platform.policy_engine import EvaluationSummary, PolicyEffect, PolicyEffectType
from app.platform.tenant import Permission, Principal, Role

pytestmark = pytest.mark.unit


def _effect(effect_type: PolicyEffectType, value: str | None = None) -> PolicyEffect:
    return PolicyEffect(type=effect_type, value=value)


@pytest.mark.parametrize(
    ("effect_type", "task_type", "priority"),
    [
        (
            PolicyEffectType.REQUIRE_HUMAN_REVIEW,
            ReviewTaskType.STANDARD_REVIEW,
            ReviewPriority.NORMAL,
        ),
        (
            PolicyEffectType.PROHIBIT_AUTOMATION,
            ReviewTaskType.STANDARD_REVIEW,
            ReviewPriority.NORMAL,
        ),
        (
            PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE,
            ReviewTaskType.EVIDENCE_REVIEW,
            ReviewPriority.NORMAL,
        ),
        (
            PolicyEffectType.FLAG_POLICY_EXCEPTION,
            ReviewTaskType.POLICY_EXCEPTION_REVIEW,
            ReviewPriority.HIGH,
        ),
        (
            PolicyEffectType.REQUIRE_MANAGER_REVIEW,
            ReviewTaskType.MANAGER_REVIEW,
            ReviewPriority.HIGH,
        ),
    ],
)
def test_effect_mapping_and_priority_are_versioned_and_deterministic(
    effect_type: PolicyEffectType,
    task_type: ReviewTaskType,
    priority: ReviewPriority,
) -> None:
    assert map_policy_effects((_effect(effect_type),)) == (task_type, priority)


def test_effect_aggregation_selects_highest_precedence_and_is_order_independent() -> None:
    effects = (
        _effect(PolicyEffectType.REQUIRE_HUMAN_REVIEW),
        _effect(PolicyEffectType.FLAG_POLICY_EXCEPTION),
        _effect(PolicyEffectType.REQUIRE_MANAGER_REVIEW),
    )
    assert map_policy_effects(effects) == (ReviewTaskType.MANAGER_REVIEW, ReviewPriority.HIGH)
    assert map_policy_effects(tuple(reversed(effects))) == map_policy_effects(effects)


@pytest.mark.parametrize(
    ("source", "action", "target"),
    [
        (ReviewTaskStatus.PENDING, ReviewActionType.CLAIMED, ReviewTaskStatus.CLAIMED),
        (ReviewTaskStatus.CLAIMED, ReviewActionType.RELEASED, ReviewTaskStatus.PENDING),
        (
            ReviewTaskStatus.CLAIMED,
            ReviewActionType.EVIDENCE_REQUESTED,
            ReviewTaskStatus.WAITING_FOR_EVIDENCE,
        ),
        (ReviewTaskStatus.WAITING_FOR_EVIDENCE, ReviewActionType.RESUMED, ReviewTaskStatus.PENDING),
        (ReviewTaskStatus.CLAIMED, ReviewActionType.ESCALATED, ReviewTaskStatus.ESCALATED),
        (ReviewTaskStatus.ESCALATED, ReviewActionType.CLAIMED, ReviewTaskStatus.CLAIMED),
        (ReviewTaskStatus.CLAIMED, ReviewActionType.RESOLVED, ReviewTaskStatus.RESOLVED),
    ],
)
def test_typed_state_machine_allows_only_declared_transitions(
    source: ReviewTaskStatus, action: ReviewActionType, target: ReviewTaskStatus
) -> None:
    assert transition(source, action) is target


@pytest.mark.parametrize(
    ("source", "action"),
    [
        (ReviewTaskStatus.PENDING, ReviewActionType.RESOLVED),
        (ReviewTaskStatus.RESOLVED, ReviewActionType.CLAIMED),
        (ReviewTaskStatus.RESOLVED, ReviewActionType.RELEASED),
        (ReviewTaskStatus.WAITING_FOR_EVIDENCE, ReviewActionType.RESOLVED),
    ],
)
def test_typed_state_machine_rejects_forbidden_transitions(
    source: ReviewTaskStatus, action: ReviewActionType
) -> None:
    with pytest.raises(InvalidReviewTransitionError):
        transition(source, action)


def test_claim_role_matrix_and_viewer_read_only_permission() -> None:
    reviewer = frozenset({Role.REVIEWER})
    admin = frozenset({Role.ADMIN})
    viewer = Principal(
        user_id="viewer",
        tenant_id="tenant",
        email="viewer@example.test",
        display_name="Viewer",
        roles=frozenset({Role.QUALITY_VIEWER}),
    )
    assert can_claim(ReviewTaskType.STANDARD_REVIEW, ReviewTaskStatus.PENDING, reviewer)
    assert not can_claim(ReviewTaskType.MANAGER_REVIEW, ReviewTaskStatus.PENDING, reviewer)
    assert can_claim(ReviewTaskType.MANAGER_REVIEW, ReviewTaskStatus.PENDING, admin)
    assert can_claim(ReviewTaskType.SAFETY_REVIEW, ReviewTaskStatus.ESCALATED, admin)
    assert viewer.has_permission(Permission.HUMAN_REVIEW_READ)
    with pytest.raises(ForbiddenError):
        viewer.require(Permission.HUMAN_REVIEW_ACTION)


def test_decision_requires_human_rationale_and_policy_basis() -> None:
    basis = DecisionBasisReference(type=DecisionBasisType.POLICY_RULE_RESULT, reference_id="rule-1")
    request = HumanDecisionRequest(
        decision=HumanDecisionType.APPROVE_EXCHANGE,
        reason_codes=(DecisionReason.POLICY_CONDITION_MET,),
        rationale="정책 조건과 검토 근거를 사람이 직접 확인했습니다.",
        basis=(basis,),
    )
    assert request.basis == (basis,)
    for rationale in ("short", "             "):
        with pytest.raises(ValidationError):
            HumanDecisionRequest(
                decision=HumanDecisionType.REJECT_REQUEST,
                reason_codes=(DecisionReason.POLICY_CONDITION_NOT_MET,),
                rationale=rationale,
                basis=(basis,),
            )
    with pytest.raises(ValidationError, match="policy rule result or policy citation"):
        HumanDecisionRequest(
            decision=HumanDecisionType.REJECT_REQUEST,
            reason_codes=(DecisionReason.EVIDENCE_INSUFFICIENT,),
            rationale="검토 가능한 정책 근거가 없어 요청을 처리할 수 없습니다.",
            basis=(
                DecisionBasisReference(
                    type=DecisionBasisType.CASE_EVIDENCE, reference_id="evidence-1"
                ),
            ),
        )


def test_other_evidence_reason_requires_explicit_rationale() -> None:
    with pytest.raises(ValidationError, match="OTHER requires rationale"):
        RequestEvidenceCommand(
            expected_version=2,
            reason_codes=(AdditionalEvidenceReason.OTHER,),
            instructions="추가 자료를 제출해 주세요.",
        )


def test_outcome_relation_is_derived_not_reviewer_supplied() -> None:
    eligible = (
        _effect(PolicyEffectType.MARK_REVIEW_ELIGIBILITY, "EXCHANGE_REVIEW"),
        _effect(PolicyEffectType.REQUIRE_HUMAN_REVIEW),
    )
    assert (
        compute_outcome_relation(
            summary=EvaluationSummary.REQUIRES_HUMAN_REVIEW,
            effects=eligible,
            decision=HumanDecisionType.APPROVE_EXCHANGE,
        )
        is OutcomeRelation.CONSISTENT_WITH_RECOMMENDATION
    )
    assert (
        compute_outcome_relation(
            summary=EvaluationSummary.REQUIRES_HUMAN_REVIEW,
            effects=eligible,
            decision=HumanDecisionType.APPROVE_REFUND,
        )
        is OutcomeRelation.DIFFERS_FROM_RECOMMENDATION
    )
    assert (
        compute_outcome_relation(
            summary=EvaluationSummary.BLOCKED_INPUT_INCOMPLETE,
            effects=eligible,
            decision=HumanDecisionType.NO_ACTION,
        )
        is OutcomeRelation.INDETERMINATE_POLICY
    )


def test_packet_hash_is_canonical_and_sensitive_to_content() -> None:
    first = canonical_hash({"task": "one", "effects": ["A", "B"]})
    reordered = canonical_hash({"effects": ["A", "B"], "task": "one"})
    changed = canonical_hash({"task": "one", "effects": ["A"]})
    assert first == reordered
    assert first != changed
    assert len(first) == 64
