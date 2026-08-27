# ADR-0071: Trace every rule to source clauses

- Status: Accepted
- Date: 2026-08-27

## Decision

Every rule references at least one same-tenant ACTIVE clause by row ID, document/version,
clause ID, and source hash. Rule-set and clause effective intervals must agree.

## Consequences

Each evaluation result can identify its curated synthetic policy basis without executing RAG text.
