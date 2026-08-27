"""Versioned deterministic policy evaluation without provider dependencies."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FIELD_REGISTRY_VERSION = "1.0.0"
OPERATOR_REGISTRY_VERSION = "1.0.0"
RULE_SCHEMA_VERSION = "1.0.0"
AGGREGATION_VERSION = "1.0.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class FieldValueType(StrEnum):
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    STRING_SET = "STRING_SET"


class PolicyField(StrEnum):
    DAYS_SINCE_PURCHASE = "case.days_since_purchase"
    ORDER_AMOUNT = "case.order_amount"
    PRODUCT_CATEGORY = "case.product_category"
    DECLARED_REQUESTED_ACTION = "case.declared_requested_action"
    HAS_ORDER_REFERENCE = "case.has_order_reference"
    HAS_PRODUCT_REFERENCE = "case.has_product_reference"
    AVAILABLE_IMAGE_COUNT = "evidence.available_image_count"
    SYSTEM_MISSING_INFORMATION = "completeness.system_missing_information"
    ISSUE_TYPES = "extraction.issue_types"
    CLAIM_COUNT = "extraction.claim_count"
    VISION_QUALIFICATION_STATUS = "vision.qualification_status"
    VISION_DETECTED_DEFECT_TYPES = "vision.detected_defect_types"
    ALIGNMENT_STATUS = "alignment.status"


class PolicyOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    CONTAINS = "CONTAINS"
    CONTAINS_ANY = "CONTAINS_ANY"
    CONTAINS_ALL = "CONTAINS_ALL"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"


class ConditionStatus(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"
    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MissingBehavior(StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleCategory(StrEnum):
    ELIGIBILITY = "ELIGIBILITY"
    EVIDENCE_REQUIREMENT = "EVIDENCE_REQUIREMENT"
    EXCEPTION = "EXCEPTION"
    ESCALATION = "ESCALATION"
    AUTOMATION_GUARD = "AUTOMATION_GUARD"


class PolicyEffectType(StrEnum):
    MARK_REVIEW_ELIGIBILITY = "MARK_REVIEW_ELIGIBILITY"
    REQUIRE_ADDITIONAL_EVIDENCE = "REQUIRE_ADDITIONAL_EVIDENCE"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    REQUIRE_MANAGER_REVIEW = "REQUIRE_MANAGER_REVIEW"
    PROHIBIT_AUTOMATION = "PROHIBIT_AUTOMATION"
    FLAG_POLICY_EXCEPTION = "FLAG_POLICY_EXCEPTION"


class RuleStatus(StrEnum):
    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvaluationSummary(StrEnum):
    EVALUATED = "EVALUATED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    REQUIRES_ADDITIONAL_EVIDENCE = "REQUIRES_ADDITIONAL_EVIDENCE"
    NO_APPLICABLE_RULE = "NO_APPLICABLE_RULE"
    BLOCKED_INPUT_INCOMPLETE = "BLOCKED_INPUT_INCOMPLETE"


class PolicyEvaluationRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SourceQualification(StrEnum):
    PRODUCTION_QUALIFIED = "PRODUCTION_QUALIFIED"
    LOCAL_POC = "LOCAL_POC"
    MOCK_QUALIFIED = "MOCK_QUALIFIED"
    REAL_MODEL_NOT_AVAILABLE = "REAL_MODEL_NOT_AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


FIELD_TYPES: Mapping[PolicyField, FieldValueType] = {
    PolicyField.DAYS_SINCE_PURCHASE: FieldValueType.INTEGER,
    PolicyField.ORDER_AMOUNT: FieldValueType.NUMBER,
    PolicyField.PRODUCT_CATEGORY: FieldValueType.STRING,
    PolicyField.DECLARED_REQUESTED_ACTION: FieldValueType.STRING,
    PolicyField.HAS_ORDER_REFERENCE: FieldValueType.BOOLEAN,
    PolicyField.HAS_PRODUCT_REFERENCE: FieldValueType.BOOLEAN,
    PolicyField.AVAILABLE_IMAGE_COUNT: FieldValueType.INTEGER,
    PolicyField.SYSTEM_MISSING_INFORMATION: FieldValueType.STRING_SET,
    PolicyField.ISSUE_TYPES: FieldValueType.STRING_SET,
    PolicyField.CLAIM_COUNT: FieldValueType.INTEGER,
    PolicyField.VISION_QUALIFICATION_STATUS: FieldValueType.STRING,
    PolicyField.VISION_DETECTED_DEFECT_TYPES: FieldValueType.STRING_SET,
    PolicyField.ALIGNMENT_STATUS: FieldValueType.STRING,
}

_ORDERED = {PolicyOperator.LT, PolicyOperator.LTE, PolicyOperator.GT, PolicyOperator.GTE}
_SET = {
    PolicyOperator.CONTAINS,
    PolicyOperator.CONTAINS_ANY,
    PolicyOperator.CONTAINS_ALL,
}
_EXISTENCE = {PolicyOperator.EXISTS, PolicyOperator.NOT_EXISTS}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class PolicyCondition(_Strict):
    field: PolicyField
    operator: PolicyOperator
    expected: Any = None
    missing_behavior: MissingBehavior

    @model_validator(mode="after")
    def validate_typed_operator(self) -> PolicyCondition:
        value_type = FIELD_TYPES[self.field]
        if self.operator in _ORDERED and value_type not in {
            FieldValueType.INTEGER,
            FieldValueType.NUMBER,
        }:
            raise ValueError("ordered operators require a numeric field")
        if self.operator in _SET and value_type is not FieldValueType.STRING_SET:
            raise ValueError("contains operators require a string-set field")
        if self.operator in {PolicyOperator.IN, PolicyOperator.NOT_IN}:
            if not isinstance(self.expected, (list, tuple)) or not self.expected:
                raise ValueError("IN operators require a non-empty expected list")
            if value_type is FieldValueType.STRING_SET or not all(
                _matches_scalar(value_type, item) for item in self.expected
            ):
                raise ValueError("IN values must match the scalar field type")
        elif self.operator in _EXISTENCE:
            if self.expected is not None:
                raise ValueError("existence operators do not accept an expected value")
        elif self.operator in {PolicyOperator.CONTAINS_ANY, PolicyOperator.CONTAINS_ALL}:
            if not _is_string_sequence(self.expected):
                raise ValueError("multi-value contains operators require strings")
        elif self.operator is PolicyOperator.CONTAINS:
            if not isinstance(self.expected, str) or not self.expected:
                raise ValueError("CONTAINS requires one non-empty string")
        elif not _matches_scalar(value_type, self.expected):
            raise ValueError("expected value does not match the field type")
        return self


class PolicyEffect(_Strict):
    type: PolicyEffectType
    value: str | None = Field(default=None, max_length=128)


class PolicySourceReference(_Strict):
    clause_id: str = Field(min_length=1, max_length=320)
    document_id: str = Field(min_length=1, max_length=255)
    document_version: str = Field(min_length=1, max_length=64)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyRule(_Strict):
    rule_id: str = Field(min_length=1, max_length=128)
    rule_version: str = Field(min_length=1, max_length=64)
    category: RuleCategory
    priority: int = Field(ge=0, le=10000)
    conditions: tuple[PolicyCondition, ...] = Field(min_length=1, max_length=30)
    effects: tuple[PolicyEffect, ...] = Field(min_length=1, max_length=20)
    requires_human_review: bool
    prohibit_final_decision: Literal[True] = True
    source_references: tuple[PolicySourceReference, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_advisory_fields(self) -> PolicyRule:
        advisory = {PolicyField.ISSUE_TYPES, PolicyField.CLAIM_COUNT}
        if (
            any(item.field in advisory for item in self.conditions)
            and not self.requires_human_review
        ):
            raise ValueError("LLM-derived fields require human review")
        return self

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class PolicyRuleSet(_Strict):
    tenant_slug: str = Field(min_length=1, max_length=128)
    rule_set_name: str = Field(min_length=1, max_length=128)
    rule_set_version: str = Field(min_length=1, max_length=64)
    effective_from: date
    effective_to: date | None = None
    source_corpus_name: str = Field(min_length=1, max_length=255)
    source_corpus_version: str = Field(min_length=1, max_length=64)
    source_corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_type: Literal["SYNTHETIC_REFERENCE"] = "SYNTHETIC_REFERENCE"
    rule_schema_version: Literal["1.0.0"] = RULE_SCHEMA_VERSION
    field_registry_version: Literal["1.0.0"] = FIELD_REGISTRY_VERSION
    operator_registry_version: Literal["1.0.0"] = OPERATOR_REGISTRY_VERSION
    aggregation_version: Literal["1.0.0"] = AGGREGATION_VERSION
    rules: tuple[PolicyRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> PolicyRuleSet:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("rule-set effective interval is invalid")
        identities = [(rule.rule_id, rule.rule_version) for rule in self.rules]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate rule identity")
        return self

    @property
    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class PolicyEvaluationInput(_Strict):
    values: Mapping[str, Any]
    llm_qualification: SourceQualification = SourceQualification.NOT_AVAILABLE
    vision_qualification: SourceQualification = SourceQualification.NOT_AVAILABLE
    alignment_qualification: SourceQualification = SourceQualification.NOT_AVAILABLE


class ConditionEvaluation(_Strict):
    condition_index: int = Field(ge=0)
    status: ConditionStatus
    actual_value: Any = None
    reason_code: str | None = None


class RuleEvaluation(_Strict):
    rule_id: str
    rule_version: str
    status: RuleStatus
    condition_results: tuple[ConditionEvaluation, ...]
    effects: tuple[PolicyEffect, ...]
    source_clause_ids: tuple[str, ...]


class PolicyEvaluation(_Strict):
    rule_set_name: str
    rule_set_version: str
    rule_set_hash: str
    summary_status: EvaluationSummary
    rule_results: tuple[RuleEvaluation, ...]
    evaluated_at: datetime | None = None


class PolicyEvaluationRun(_Strict):
    id: str
    tenant_id: str
    case_id: str
    analysis_run_id: str
    rule_set_id: str
    rule_set_name: str
    rule_set_version: str
    rule_set_hash: str
    as_of_date: date
    status: PolicyEvaluationRunStatus
    summary_status: EvaluationSummary | None = None
    correlation_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


def evaluate_condition(
    condition: PolicyCondition,
    input_value: PolicyEvaluationInput,
    *,
    condition_index: int = 0,
) -> ConditionEvaluation:
    if condition.field is PolicyField.VISION_DETECTED_DEFECT_TYPES and (
        input_value.vision_qualification is not SourceQualification.PRODUCTION_QUALIFIED
    ):
        return ConditionEvaluation(
            condition_index=condition_index,
            status=ConditionStatus.NOT_EVALUATED,
            reason_code="VISION_MODEL_NOT_QUALIFIED",
        )
    if condition.field is PolicyField.ALIGNMENT_STATUS and (
        input_value.alignment_qualification is not SourceQualification.PRODUCTION_QUALIFIED
    ):
        return ConditionEvaluation(
            condition_index=condition_index,
            status=ConditionStatus.NOT_EVALUATED,
            reason_code="ALIGNMENT_NOT_QUALIFIED",
        )
    present = condition.field.value in input_value.values
    actual = input_value.values.get(condition.field.value)
    if condition.operator in _EXISTENCE:
        matched = (
            (present and actual is not None)
            if condition.operator is PolicyOperator.EXISTS
            else (not present or actual is None)
        )
        return ConditionEvaluation(
            condition_index=condition_index,
            status=ConditionStatus.SATISFIED if matched else ConditionStatus.UNSATISFIED,
            actual_value=actual,
        )
    if not present or actual is None:
        return ConditionEvaluation(
            condition_index=condition_index,
            status=ConditionStatus(condition.missing_behavior.value),
            reason_code="INPUT_MISSING",
        )
    if not _matches_input(FIELD_TYPES[condition.field], actual):
        return ConditionEvaluation(
            condition_index=condition_index,
            status=ConditionStatus.UNKNOWN,
            reason_code="INPUT_TYPE_MISMATCH",
        )
    matched = _apply_operator(condition.operator, actual, condition.expected)
    return ConditionEvaluation(
        condition_index=condition_index,
        status=ConditionStatus.SATISFIED if matched else ConditionStatus.UNSATISFIED,
        actual_value=actual,
    )


def evaluate_rule(rule: PolicyRule, input_value: PolicyEvaluationInput) -> RuleEvaluation:
    results = tuple(
        evaluate_condition(condition, input_value, condition_index=index)
        for index, condition in enumerate(rule.conditions)
    )
    statuses = {item.status for item in results}
    if ConditionStatus.UNSATISFIED in statuses:
        status = RuleStatus.NOT_MATCHED
    elif statuses == {ConditionStatus.NOT_APPLICABLE}:
        status = RuleStatus.NOT_APPLICABLE
    elif statuses <= {ConditionStatus.SATISFIED, ConditionStatus.NOT_APPLICABLE} and (
        ConditionStatus.SATISFIED in statuses
    ):
        status = RuleStatus.MATCHED
    else:
        status = RuleStatus.INDETERMINATE
    effects = rule.effects if status is RuleStatus.MATCHED else ()
    if status is RuleStatus.INDETERMINATE:
        safe_types = {
            PolicyEffectType.REQUIRE_HUMAN_REVIEW,
            PolicyEffectType.PROHIBIT_AUTOMATION,
        }
        effects = tuple(effect for effect in rule.effects if effect.type in safe_types)
        review = PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW)
        effects = tuple(dict.fromkeys((*effects, review)))
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        status=status,
        condition_results=results,
        effects=effects,
        source_clause_ids=tuple(ref.clause_id for ref in rule.source_references),
    )


def evaluate_rule_set(
    rule_set: PolicyRuleSet, input_value: PolicyEvaluationInput
) -> PolicyEvaluation:
    results = tuple(
        evaluate_rule(rule, input_value)
        for rule in sorted(rule_set.rules, key=lambda value: (-value.priority, value.rule_id))
    )
    applicable = tuple(
        result for result in results if result.status is not RuleStatus.NOT_APPLICABLE
    )
    effects = {effect.type for result in applicable for effect in result.effects}
    if not applicable:
        summary = EvaluationSummary.NO_APPLICABLE_RULE
    elif PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE in effects:
        summary = EvaluationSummary.REQUIRES_ADDITIONAL_EVIDENCE
    elif (
        PolicyEffectType.REQUIRE_HUMAN_REVIEW in effects
        or PolicyEffectType.REQUIRE_MANAGER_REVIEW in effects
        or any(result.status is RuleStatus.INDETERMINATE for result in applicable)
    ):
        summary = EvaluationSummary.REQUIRES_HUMAN_REVIEW
    elif any(result.status is RuleStatus.MATCHED for result in applicable):
        summary = EvaluationSummary.EVALUATED
    else:
        summary = EvaluationSummary.EVALUATED
    return PolicyEvaluation(
        rule_set_name=rule_set.rule_set_name,
        rule_set_version=rule_set.rule_set_version,
        rule_set_hash=rule_set.content_hash,
        summary_status=summary,
        rule_results=results,
    )


def _is_string_sequence(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
    )


def _matches_scalar(value_type: FieldValueType, value: object) -> bool:
    if value_type is FieldValueType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type is FieldValueType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type is FieldValueType.BOOLEAN:
        return isinstance(value, bool)
    if value_type is FieldValueType.STRING:
        return isinstance(value, str) and bool(value)
    return False


def _matches_input(value_type: FieldValueType, value: object) -> bool:
    if value_type is FieldValueType.STRING_SET:
        return isinstance(value, (list, tuple, set)) and all(
            isinstance(item, str) and bool(item) for item in value
        )
    return _matches_scalar(value_type, value)


def _apply_operator(operator: PolicyOperator, actual: object, expected: object) -> bool:
    if operator is PolicyOperator.EQ:
        return actual == expected
    if operator is PolicyOperator.NE:
        return actual != expected
    if operator is PolicyOperator.LT:
        return bool(actual < expected)  # type: ignore[operator]
    if operator is PolicyOperator.LTE:
        return bool(actual <= expected)  # type: ignore[operator]
    if operator is PolicyOperator.GT:
        return bool(actual > expected)  # type: ignore[operator]
    if operator is PolicyOperator.GTE:
        return bool(actual >= expected)  # type: ignore[operator]
    if operator is PolicyOperator.IN:
        return actual in expected  # type: ignore[operator]
    if operator is PolicyOperator.NOT_IN:
        return actual not in expected  # type: ignore[operator]
    if operator is PolicyOperator.CONTAINS:
        return expected in actual  # type: ignore[operator]
    if operator is PolicyOperator.CONTAINS_ANY:
        return bool(set(actual) & set(expected))  # type: ignore[arg-type]
    if operator is PolicyOperator.CONTAINS_ALL:
        return set(expected) <= set(actual)  # type: ignore[arg-type]
    if operator is PolicyOperator.EXISTS:
        return True
    if operator is PolicyOperator.NOT_EXISTS:
        return False
    raise AssertionError("unreachable operator")


__all__ = [
    "AGGREGATION_VERSION",
    "FIELD_REGISTRY_VERSION",
    "FIELD_TYPES",
    "OPERATOR_REGISTRY_VERSION",
    "RULE_SCHEMA_VERSION",
    "ConditionEvaluation",
    "ConditionStatus",
    "EvaluationSummary",
    "FieldValueType",
    "MissingBehavior",
    "PolicyCondition",
    "PolicyEffect",
    "PolicyEffectType",
    "PolicyEvaluation",
    "PolicyEvaluationInput",
    "PolicyEvaluationRun",
    "PolicyEvaluationRunStatus",
    "PolicyField",
    "PolicyOperator",
    "PolicyRule",
    "PolicyRuleSet",
    "PolicySourceReference",
    "RuleCategory",
    "RuleEvaluation",
    "RuleStatus",
    "SourceQualification",
    "canonical_hash",
    "evaluate_condition",
    "evaluate_rule",
    "evaluate_rule_set",
]
