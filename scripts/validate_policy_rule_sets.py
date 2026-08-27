"""Fail-closed validation for synthetic rule sets and source clause traceability."""

from __future__ import annotations

import json
from pathlib import Path

from app.platform.policy_engine import PolicyField, PolicyRuleSet, canonical_hash

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/policy_rules/normalized/policy_rule_sets_v1.jsonl"
MANIFEST = ROOT / "data/policy_rules/manifests/policy_rule_sets_v1.json"
CLAUSES = ROOT / "data/policy_corpus/clauses/policy_clauses_v1.jsonl"


def main() -> int:
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in RULES.read_text(encoding="utf-8").splitlines()
        if line
    )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    clauses = {
        (row["tenant_id"], row["clause_id"]): row
        for line in CLAUSES.read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    }
    if len(rule_sets) != 2 or sum(len(item.rules) for item in rule_sets) < 24:
        raise SystemExit("policy rule-set count gate failed")
    identities: set[tuple[str, str, str]] = set()
    for rule_set in rule_sets:
        identity = (rule_set.tenant_slug, rule_set.rule_set_name, rule_set.rule_set_version)
        if identity in identities:
            raise SystemExit("duplicate rule-set version")
        identities.add(identity)
        for rule in rule_set.rules:
            if not rule.conditions or not rule.effects or not rule.source_references:
                raise SystemExit("empty rule component")
            for source in rule.source_references:
                clause = clauses.get((rule_set.tenant_slug, source.clause_id))
                if clause is None:
                    raise SystemExit("missing or cross-tenant source clause")
                if (
                    clause["document_id"] != source.document_id
                    or clause["document_version"] != source.document_version
                    or clause["source_hash"] != source.source_hash
                    or clause["document_status"] != "ACTIVE"
                ):
                    raise SystemExit("wrong source document version or hash")
            forbidden_hard = {
                "extraction.requested_actions",
                "extraction.text_ambiguities",
            }
            if any(condition.field.value in forbidden_hard for condition in rule.conditions):
                raise SystemExit("unqualified Local LLM field used as hard input")
            if any(
                condition.field in {PolicyField.ISSUE_TYPES, PolicyField.CLAIM_COUNT}
                for condition in rule.conditions
            ) and not (rule.requires_human_review and rule.prohibit_final_decision):
                raise SystemExit("advisory LLM rule lacks mandatory review")
    content_hash = canonical_hash([item.model_dump(mode="json") for item in rule_sets])
    if content_hash != manifest["content_hash"]:
        raise SystemExit("rule-set manifest content hash mismatch")
    print(
        json.dumps(
            {
                "status": "POLICY_RULE_SET_VALID",
                "tenant_count": len(rule_sets),
                "rule_set_count": len(rule_sets),
                "rule_count": sum(len(item.rules) for item in rule_sets),
                "source_clause_count": sum(
                    len(rule.source_references) for item in rule_sets for rule in item.rules
                ),
                "content_hash": content_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
