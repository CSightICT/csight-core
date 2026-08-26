# ADR-0048: Defer grounded generation to Sprint 4C-3

- Status: Accepted
- Date: 2026-08-26

## Decision

Citation packs, grounded explanations, unsupported-claim checks and injection evaluation start only
after retrieval/query-builder profiles are independently locked.

## Consequences

Sprint 4C-1 exposes clauses and ranking metadata only; it creates no decision or generated answer.
