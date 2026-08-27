# ADR-0089: Case Resolution has a separate lifecycle from Case

- Status: Accepted
- Date: 2026-08-27

## Decision

Sprint 5C stores one CAS Resolution Projection per Case and append-only Resolution Events. Resolution
status never mutates or duplicates `cases.status`, and no Resolution state closes a Case.

## Consequences

Post-decision progress can be retried and audited without mixing intake state with execution state.
Reads must join Case and Resolution projections. Case Closure remains outside Sprint 5C.
