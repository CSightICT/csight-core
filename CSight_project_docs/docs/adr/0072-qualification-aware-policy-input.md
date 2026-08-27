# ADR-0072: Policy inputs are qualification-aware

- Status: Accepted
- Date: 2026-08-27

## Decision

Input snapshots record LLM, Vision, and Alignment qualification scopes. Evaluators use those
scopes explicitly and may return `NOT_EVALUATED` instead of treating unqualified output as fact.

## Consequences

Runtime output exposes source limitations and fails safely as provider qualification evolves.
