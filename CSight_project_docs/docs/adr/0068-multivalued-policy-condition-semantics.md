# ADR-0068: Define multi-valued policy condition semantics

- Status: Accepted
- Date: 2026-08-27

## Decision

`CONTAINS`, `CONTAINS_ANY`, and `CONTAINS_ALL` operate only on validated string sets. Missing
values use an explicit `UNKNOWN`, `NOT_EVALUATED`, or `NOT_APPLICABLE` behavior and are never
silently coerced to false.

## Consequences

Condition outcomes remain auditable across absent and multi-valued inputs.
