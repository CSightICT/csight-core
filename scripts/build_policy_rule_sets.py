"""Build two deterministic synthetic policy rule sets from existing policy clauses."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from app.platform.policy_engine import (
    MissingBehavior,
    PolicyCondition,
    PolicyEffect,
    PolicyEffectType,
    PolicyField,
    PolicyOperator,
    PolicyRule,
    PolicyRuleSet,
    PolicySourceReference,
    RuleCategory,
    canonical_hash,
)

ROOT = Path(__file__).resolve().parents[1]
CLAUSES = ROOT / "data/policy_corpus/clauses/policy_clauses_v1.jsonl"
CORPUS_MANIFEST = ROOT / "data/policy_corpus/manifests/policy_corpus_v1.json"
OUTPUT = ROOT / "data/policy_rules/normalized/policy_rule_sets_v1.jsonl"
MANIFEST = ROOT / "data/policy_rules/manifests/policy_rule_sets_v1.json"
REPORT_JSON = ROOT / "data/policy_rules/reports/policy_rule_sets_quality_v1.json"
REPORT_MD = ROOT / "data/policy_rules/reports/policy_rule_sets_quality_v1.md"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _source(row: dict[str, Any]) -> PolicySourceReference:
    return PolicySourceReference(
        clause_id=row["clause_id"],
        document_id=row["document_id"],
        document_version=row["document_version"],
        source_hash=row["source_hash"],
    )


def _condition(
    field: PolicyField,
    operator: PolicyOperator,
    expected: object,
    missing: MissingBehavior = MissingBehavior.UNKNOWN,
) -> PolicyCondition:
    return PolicyCondition(
        field=field,
        operator=operator,
        expected=expected,
        missing_behavior=missing,
    )


def _rule(
    *,
    tenant_code: str,
    index: int,
    source: dict[str, Any],
) -> PolicyRule:
    templates: tuple[
        tuple[RuleCategory, tuple[PolicyCondition, ...], tuple[PolicyEffect, ...], bool], ...
    ] = (
        (
            RuleCategory.ELIGIBILITY,
            (_condition(PolicyField.DAYS_SINCE_PURCHASE, PolicyOperator.LTE, 14),),
            (PolicyEffect(type=PolicyEffectType.MARK_REVIEW_ELIGIBILITY, value="RETURN_REVIEW"),),
            False,
        ),
        (
            RuleCategory.ELIGIBILITY,
            (
                _condition(
                    PolicyField.DECLARED_REQUESTED_ACTION,
                    PolicyOperator.IN,
                    ["RETURN", "EXCHANGE", "REFUND"],
                ),
            ),
            (PolicyEffect(type=PolicyEffectType.MARK_REVIEW_ELIGIBILITY, value="ACTION_REVIEW"),),
            False,
        ),
        (
            RuleCategory.EVIDENCE_REQUIREMENT,
            (_condition(PolicyField.AVAILABLE_IMAGE_COUNT, PolicyOperator.EQ, 0),),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE),),
            False,
        ),
        (
            RuleCategory.EVIDENCE_REQUIREMENT,
            (_condition(PolicyField.HAS_ORDER_REFERENCE, PolicyOperator.EQ, False),),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE),),
            False,
        ),
        (
            RuleCategory.EVIDENCE_REQUIREMENT,
            (_condition(PolicyField.HAS_PRODUCT_REFERENCE, PolicyOperator.EQ, False),),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_ADDITIONAL_EVIDENCE),),
            False,
        ),
        (
            RuleCategory.EXCEPTION,
            (_condition(PolicyField.ORDER_AMOUNT, PolicyOperator.GT, 100000),),
            (
                PolicyEffect(type=PolicyEffectType.REQUIRE_MANAGER_REVIEW),
                PolicyEffect(type=PolicyEffectType.PROHIBIT_AUTOMATION),
            ),
            True,
        ),
        (
            RuleCategory.ESCALATION,
            (
                _condition(
                    PolicyField.SYSTEM_MISSING_INFORMATION,
                    PolicyOperator.CONTAINS_ANY,
                    ["ORDER_REFERENCE", "PRODUCT_REFERENCE"],
                ),
            ),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),),
            True,
        ),
        (
            RuleCategory.EXCEPTION,
            (_condition(PolicyField.ISSUE_TYPES, PolicyOperator.CONTAINS, "LEAKAGE"),),
            (
                PolicyEffect(type=PolicyEffectType.FLAG_POLICY_EXCEPTION, value="LEAKAGE"),
                PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),
            ),
            True,
        ),
        (
            RuleCategory.EXCEPTION,
            (_condition(PolicyField.ISSUE_TYPES, PolicyOperator.CONTAINS, "BREAKAGE"),),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),),
            True,
        ),
        (
            RuleCategory.AUTOMATION_GUARD,
            (
                _condition(
                    PolicyField.VISION_DETECTED_DEFECT_TYPES,
                    PolicyOperator.CONTAINS_ANY,
                    ["LEAKAGE", "BREAKAGE"],
                    MissingBehavior.NOT_EVALUATED,
                ),
            ),
            (
                PolicyEffect(type=PolicyEffectType.PROHIBIT_AUTOMATION),
                PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),
            ),
            True,
        ),
        (
            RuleCategory.AUTOMATION_GUARD,
            (_condition(PolicyField.CLAIM_COUNT, PolicyOperator.GT, 1),),
            (
                PolicyEffect(type=PolicyEffectType.PROHIBIT_AUTOMATION),
                PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),
            ),
            True,
        ),
        (
            RuleCategory.ESCALATION,
            (
                _condition(
                    PolicyField.ALIGNMENT_STATUS,
                    PolicyOperator.EQ,
                    "ALIGNED",
                    MissingBehavior.NOT_EVALUATED,
                ),
            ),
            (PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),),
            True,
        ),
    )
    category, conditions, effects, review = templates[index]
    return PolicyRule(
        rule_id=f"{tenant_code}-POLICY-{index + 1:03d}",
        rule_version="1.0.0",
        category=category,
        priority=1000 - index * 10,
        conditions=conditions,
        effects=effects,
        requires_human_review=review,
        source_references=(_source(source),),
    )


def build() -> tuple[PolicyRuleSet, ...]:
    corpus_manifest = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    active = [row for row in _read_jsonl(CLAUSES) if row["document_status"] == "ACTIVE"]
    tenants = sorted({row["tenant_id"] for row in active})
    output: list[PolicyRuleSet] = []
    for tenant in tenants:
        sources = [row for row in active if row["tenant_id"] == tenant]
        sources.sort(key=lambda row: row["clause_id"])
        if len(sources) < 12:
            raise SystemExit(f"tenant {tenant} has fewer than 12 active source clauses")
        code = "BRD" if tenant.endswith("brand") else "RTL"
        output.append(
            PolicyRuleSet(
                tenant_slug=tenant,
                rule_set_name="product_defect_policy",
                rule_set_version="1.0.0",
                effective_from=date(2026, 1, 1),
                source_corpus_name=corpus_manifest["corpus_name"],
                source_corpus_version=corpus_manifest["corpus_version"],
                source_corpus_hash=corpus_manifest["source_hash"],
                rules=tuple(
                    _rule(tenant_code=code, index=index, source=sources[index])
                    for index in range(12)
                ),
            )
        )
    return tuple(output)


def main() -> int:
    rule_sets = build()
    for path in (OUTPUT, MANIFEST, REPORT_JSON, REPORT_MD):
        path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for item in rule_sets
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rule_count = sum(len(item.rules) for item in rule_sets)
    payload_hash = canonical_hash([item.model_dump(mode="json") for item in rule_sets])
    manifest = {
        "dataset": "policy_rule_sets_v1",
        "schema_version": "1.0.0",
        "builder_version": "1.0.0",
        "tenant_count": len(rule_sets),
        "rule_set_count": len(rule_sets),
        "rule_count": rule_count,
        "source_clause_count": rule_count,
        "content_hash": payload_hash,
        "source_type": "SYNTHETIC_REFERENCE",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    categories = Counter(rule.category.value for item in rule_sets for rule in item.rules)
    report = {**manifest, "category_distribution": dict(sorted(categories.items()))}
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_MD.write_text(
        "# Synthetic Policy Rule Set v1\n\n"
        f"- Tenants: {len(rule_sets)}\n- Rule sets: {len(rule_sets)}\n"
        f"- Rules/source clauses: {rule_count}/{rule_count}\n"
        f"- Content hash: `{payload_hash}`\n"
        "- Scope: synthetic reference only; no legal or enterprise-policy authority.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
