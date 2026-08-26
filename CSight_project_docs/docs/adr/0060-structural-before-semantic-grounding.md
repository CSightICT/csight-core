# ADR-0060: Separate structural grounding qualification from semantic faithfulness

- Status: Accepted
- Date: 2026-08-27

## Decision

Sprint 4C-3A qualifies deterministic schema, citation allowlist, tenant/version, forbidden-field,
duplicate-normalization, injection-contract, and replay checks. Semantic citation precision/recall,
unsupported-claim rate, and paraphrase faithfulness remain skipped until a pinned real LLM is run.

## Consequences

Mock generation is orchestration evidence only. Structural success is never reported as proof that a
model statement is semantically supported by the cited policy text.
