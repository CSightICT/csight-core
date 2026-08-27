from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.platform.policy_engine import (
    ConditionStatus,
    EvaluationSummary,
    MissingBehavior,
    PolicyCondition,
    PolicyEffect,
    PolicyEffectType,
    PolicyEvaluationInput,
    PolicyField,
    PolicyOperator,
    PolicyRule,
    PolicyRuleSet,
    PolicySourceReference,
    RuleCategory,
    RuleStatus,
    SourceQualification,
    evaluate_condition,
    evaluate_rule_set,
)


def _source() -> PolicySourceReference:
    return PolicySourceReference(
        clause_id="POLICY-RETURN-001:1.0.0:C1",
        document_id="POLICY-RETURN-001",
        document_version="1.0.0",
        source_hash="a" * 64,
    )


def _rule(*conditions: PolicyCondition) -> PolicyRule:
    return PolicyRule(
        rule_id="RETURN-001",
        rule_version="1.0.0",
        category=RuleCategory.ELIGIBILITY,
        priority=100,
        conditions=conditions,
        effects=(PolicyEffect(type=PolicyEffectType.MARK_REVIEW_ELIGIBILITY),),
        requires_human_review=False,
        source_references=(_source(),),
    )


def _set(rule: PolicyRule) -> PolicyRuleSet:
    return PolicyRuleSet(
        tenant_slug="tenant-a",
        rule_set_name="product_defect_policy",
        rule_set_version="1.0.0",
        effective_from=date(2026, 1, 1),
        source_corpus_name="synthetic_policy_reference",
        source_corpus_version="1.0.0",
        source_corpus_hash="b" * 64,
        rules=(rule,),
    )


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "status"),
    [
        (PolicyOperator.EQ, "GENERAL", "GENERAL", ConditionStatus.SATISFIED),
        (PolicyOperator.LTE, 3, 7, ConditionStatus.SATISFIED),
        (PolicyOperator.LTE, 9, 7, ConditionStatus.UNSATISFIED),
        (PolicyOperator.CONTAINS, ["LEAKAGE"], "LEAKAGE", ConditionStatus.SATISFIED),
        (PolicyOperator.EXISTS, 1, None, ConditionStatus.SATISFIED),
    ],
)
def test_typed_operators(
    operator: PolicyOperator,
    actual: Any,
    expected: Any,
    status: ConditionStatus,
) -> None:
    field = {
        PolicyOperator.EQ: PolicyField.PRODUCT_CATEGORY,
        PolicyOperator.LTE: PolicyField.DAYS_SINCE_PURCHASE,
        PolicyOperator.CONTAINS: PolicyField.ISSUE_TYPES,
        PolicyOperator.EXISTS: PolicyField.CLAIM_COUNT,
    }[operator]
    condition = PolicyCondition(
        field=field,
        operator=operator,
        expected=expected,
        missing_behavior=MissingBehavior.UNKNOWN,
    )
    result = evaluate_condition(condition, PolicyEvaluationInput(values={field.value: actual}))
    assert result.status is status


def test_missing_behavior_is_not_implicitly_false() -> None:
    for behavior in MissingBehavior:
        condition = PolicyCondition(
            field=PolicyField.DAYS_SINCE_PURCHASE,
            operator=PolicyOperator.LTE,
            expected=7,
            missing_behavior=behavior,
        )
        result = evaluate_condition(condition, PolicyEvaluationInput(values={}))
        assert result.status.value == behavior.value


def test_not_exists_and_runtime_input_type_mismatch_are_explicit() -> None:
    absent = PolicyCondition(
        field=PolicyField.PRODUCT_CATEGORY,
        operator=PolicyOperator.NOT_EXISTS,
        expected=None,
        missing_behavior=MissingBehavior.UNKNOWN,
    )
    assert (
        evaluate_condition(absent, PolicyEvaluationInput(values={})).status
        is ConditionStatus.SATISFIED
    )
    typed = PolicyCondition(
        field=PolicyField.DAYS_SINCE_PURCHASE,
        operator=PolicyOperator.LTE,
        expected=7,
        missing_behavior=MissingBehavior.UNKNOWN,
    )
    result = evaluate_condition(
        typed,
        PolicyEvaluationInput(values={PolicyField.DAYS_SINCE_PURCHASE.value: "three"}),
    )
    assert result.status is ConditionStatus.UNKNOWN
    assert result.reason_code == "INPUT_TYPE_MISMATCH"


def test_mock_vision_dependency_is_not_evaluated() -> None:
    condition = PolicyCondition(
        field=PolicyField.VISION_DETECTED_DEFECT_TYPES,
        operator=PolicyOperator.CONTAINS,
        expected="LEAKAGE",
        missing_behavior=MissingBehavior.UNKNOWN,
    )
    result = evaluate_condition(
        condition,
        PolicyEvaluationInput(
            values={condition.field.value: ["LEAKAGE"]},
            vision_qualification=SourceQualification.MOCK_QUALIFIED,
        ),
    )
    assert result.status is ConditionStatus.NOT_EVALUATED
    assert result.reason_code == "VISION_MODEL_NOT_QUALIFIED"


def test_llm_issue_rule_requires_human_review() -> None:
    with pytest.raises(ValidationError, match="LLM-derived"):
        _rule(
            PolicyCondition(
                field=PolicyField.ISSUE_TYPES,
                operator=PolicyOperator.CONTAINS,
                expected="LEAKAGE",
                missing_behavior=MissingBehavior.UNKNOWN,
            )
        )


def test_unknown_field_operator_type_and_final_effect_fail_closed() -> None:
    base = {
        "field": "case.days_since_purchase",
        "operator": "LTE",
        "expected": 7,
        "missing_behavior": "UNKNOWN",
    }
    with pytest.raises(ValidationError):
        PolicyCondition.model_validate({**base, "field": "case.arbitrary"})
    with pytest.raises(ValidationError):
        PolicyCondition.model_validate({**base, "operator": "PYTHON"})
    with pytest.raises(ValidationError, match="field type"):
        PolicyCondition.model_validate({**base, "expected": "seven"})
    with pytest.raises(ValidationError):
        PolicyEffect.model_validate({"type": "APPROVE_REFUND"})


def test_missing_source_duplicate_rule_and_final_decision_override_fail_closed() -> None:
    condition = PolicyCondition(
        field=PolicyField.DAYS_SINCE_PURCHASE,
        operator=PolicyOperator.LTE,
        expected=7,
        missing_behavior=MissingBehavior.UNKNOWN,
    )
    payload = _rule(condition).model_dump(mode="json")
    with pytest.raises(ValidationError):
        PolicyRule.model_validate({**payload, "source_references": []})
    with pytest.raises(ValidationError):
        PolicyRule.model_validate({**payload, "prohibit_final_decision": False})
    rule = _rule(condition)
    rule_set_payload = _set(rule).model_dump(mode="json")
    with pytest.raises(ValidationError, match="duplicate rule identity"):
        PolicyRuleSet.model_validate({**rule_set_payload, "rules": [payload, payload]})


def test_rule_aggregation_hash_and_replay_are_stable() -> None:
    rule = _rule(
        PolicyCondition(
            field=PolicyField.DAYS_SINCE_PURCHASE,
            operator=PolicyOperator.LTE,
            expected=7,
            missing_behavior=MissingBehavior.UNKNOWN,
        )
    )
    rule_set = _set(rule)
    input_value = PolicyEvaluationInput(values={PolicyField.DAYS_SINCE_PURCHASE.value: 3})
    first = evaluate_rule_set(rule_set, input_value)
    second = evaluate_rule_set(rule_set, input_value)
    assert first == second
    assert first.rule_set_hash == rule_set.content_hash
    assert first.rule_results[0].status is RuleStatus.MATCHED
    assert first.summary_status is EvaluationSummary.EVALUATED


def test_indeterminate_rule_forces_human_review_without_final_decision() -> None:
    rule = _rule(
        PolicyCondition(
            field=PolicyField.DAYS_SINCE_PURCHASE,
            operator=PolicyOperator.LTE,
            expected=7,
            missing_behavior=MissingBehavior.UNKNOWN,
        )
    )
    result = evaluate_rule_set(_set(rule), PolicyEvaluationInput(values={}))
    item = result.rule_results[0]
    assert item.status is RuleStatus.INDETERMINATE
    assert PolicyEffectType.REQUIRE_HUMAN_REVIEW in {effect.type for effect in item.effects}
    assert result.summary_status is EvaluationSummary.REQUIRES_HUMAN_REVIEW
    serialized = result.model_dump_json()
    assert all(value not in serialized for value in ("APPROVED", "REJECTED", "FRAUD"))
