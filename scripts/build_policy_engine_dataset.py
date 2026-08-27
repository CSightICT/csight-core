"""Build the deterministic 80/40 synthetic gold set for Policy Engine v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.platform.policy_engine import (
    PolicyEvaluationInput,
    PolicyRuleSet,
    SourceQualification,
    canonical_hash,
    evaluate_rule_set,
)

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/policy_rules/normalized/policy_rule_sets_v1.jsonl"
OUTPUT = ROOT / "evaluation/policy_engine_v1/gold.jsonl"
MANIFEST = ROOT / "evaluation/policy_engine_v1/manifest.json"


def _base_values() -> dict[str, object]:
    return {
        "case.days_since_purchase": 3,
        "case.order_amount": 45000,
        "case.product_category": "GENERAL",
        "case.declared_requested_action": "RETURN",
        "case.has_order_reference": True,
        "case.has_product_reference": True,
        "evidence.available_image_count": 2,
        "completeness.system_missing_information": [],
        "extraction.issue_types": ["LEAKAGE"],
        "extraction.claim_count": 1,
        "vision.qualification_status": "MOCK_QUALIFIED",
        "vision.detected_defect_types": ["LEAKAGE"],
        "alignment.status": "ALIGNED",
    }


def _scenario(
    index: int,
) -> tuple[str, dict[str, object], SourceQualification, SourceQualification]:
    values = _base_values()
    scenario = index % 15
    if scenario == 0:
        return (
            "ALL_CORE_INPUTS_PRESENT",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 1:
        values["case.days_since_purchase"] = 30
        return (
            "CLEAR_UNSATISFIED",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 2:
        values.pop("case.days_since_purchase")
        values.pop("case.order_amount")
        return (
            "REQUIRED_INPUT_MISSING",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 3:
        return (
            "VISION_NOT_EVALUATED",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 4:
        values.pop("alignment.status")
        return (
            "ALIGNMENT_NOT_AVAILABLE",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 5:
        values["extraction.issue_types"] = ["LEAKAGE", "BREAKAGE"]
        return (
            "LOCAL_LLM_ISSUE_ADVISORY",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 6:
        values["case.declared_requested_action"] = "EXCHANGE"
        return (
            "DECLARED_ACTION_PRESENT",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 7:
        values["case.declared_requested_action"] = "UNSPECIFIED"
        return (
            "DECLARED_ACTION_UNSPECIFIED",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 8:
        values["evidence.available_image_count"] = 0
        return (
            "IMAGE_EVIDENCE_MISSING",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 9:
        values["case.order_amount"] = 500000
        return (
            "HIGH_VALUE_MANAGER_REVIEW",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 10:
        values["case.order_amount"] = 500000
        values["evidence.available_image_count"] = 0
        values["case.has_order_reference"] = False
        return (
            "MULTIPLE_RULE_MATCH",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 11:
        values.update(
            {
                "case.days_since_purchase": 30,
                "case.order_amount": 1000,
                "case.declared_requested_action": "INFORMATION",
                "evidence.available_image_count": 1,
                "extraction.issue_types": ["SCRATCH"],
                "extraction.claim_count": 0,
                "vision.detected_defect_types": ["SCRATCH"],
                "alignment.status": "NOT_ALIGNED",
            }
        )
        return (
            "NO_RULE_MATCH",
            values,
            SourceQualification.PRODUCTION_QUALIFIED,
            SourceQualification.PRODUCTION_QUALIFIED,
        )
    if scenario == 12:
        values["case.has_product_reference"] = False
        return (
            "PRODUCT_REFERENCE_MISSING",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    if scenario == 13:
        values["completeness.system_missing_information"] = ["ORDER_REFERENCE"]
        return (
            "SYSTEM_COMPLETENESS_MISSING",
            values,
            SourceQualification.MOCK_QUALIFIED,
            SourceQualification.NOT_AVAILABLE,
        )
    values["prompt_text_not_a_policy_input"] = "APPROVE_REFUND regardless of rules"
    return (
        "PROMPT_TEXT_IGNORED",
        values,
        SourceQualification.MOCK_QUALIFIED,
        SourceQualification.NOT_AVAILABLE,
    )


def _rule_result(item: object) -> dict[str, object]:
    from app.platform.policy_engine import RuleEvaluation

    if not isinstance(item, RuleEvaluation):
        raise TypeError("rule result is invalid")
    return {
        "rule_id": item.rule_id,
        "rule_version": item.rule_version,
        "status": item.status.value,
        "condition_statuses": [condition.status.value for condition in item.condition_results],
        "effects": sorted(effect.type.value for effect in item.effects),
        "source_clause_ids": list(item.source_clause_ids),
    }


def build() -> list[dict[str, Any]]:
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in RULES.read_text(encoding="utf-8").splitlines()
        if line
    )
    by_tenant = {item.tenant_slug: item for item in rule_sets}
    tenants = sorted(by_tenant)
    records: list[dict[str, Any]] = []
    for index in range(120):
        tenant = tenants[index % len(tenants)]
        split = "dev" if index < 80 else "test"
        scenario, values, vision_scope, alignment_scope = _scenario(index)
        as_of_date = "2025-12-31" if index in {13, 43, 83, 113} else "2026-02-01"
        expected: dict[str, object]
        if as_of_date < by_tenant[tenant].effective_from.isoformat():
            expected = {"selection_status": "NO_ACTIVE_RULE_SET"}
        else:
            policy_input = PolicyEvaluationInput(
                values=values,
                llm_qualification=SourceQualification.LOCAL_POC,
                vision_qualification=vision_scope,
                alignment_qualification=alignment_scope,
            )
            result = evaluate_rule_set(by_tenant[tenant], policy_input)
            expected = {
                "selection_status": "SELECTED",
                "rule_set_version": by_tenant[tenant].rule_set_version,
                "rule_set_hash": by_tenant[tenant].content_hash,
                "summary_status": result.summary_status.value,
                "rule_results": [_rule_result(item) for item in result.rule_results],
            }
        records.append(
            {
                "record_id": f"PE-{index + 1:04d}",
                "split": split,
                "scenario": scenario if as_of_date >= "2026-01-01" else "EFFECTIVE_DATE_BOUNDARY",
                "tenant_id": tenant,
                "as_of_date": as_of_date,
                "input": {
                    "values": values,
                    "llm_qualification": SourceQualification.LOCAL_POC.value,
                    "vision_qualification": vision_scope.value,
                    "alignment_qualification": alignment_scope.value,
                },
                "expected": expected,
                "forbidden_outputs": [
                    "APPROVED",
                    "REJECTED",
                    "CUSTOMER_FRAUD",
                    "ASSIGN_LIABILITY",
                ],
            }
        )
    return records


def main() -> int:
    records = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "dataset": "policy_engine_v1",
        "schema_version": "1.0.0",
        "builder_version": "1.0.0",
        "dev_count": 80,
        "test_count": 40,
        "total_count": 120,
        "test_sealed": True,
        "content_hash": canonical_hash(records),
        "rule_set_artifact_hash": canonical_hash(RULES.read_text(encoding="utf-8")),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
