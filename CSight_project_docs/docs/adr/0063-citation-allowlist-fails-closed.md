# ADR-0063: Citation allowlist validation fails closed before persistence

- Status: Accepted
- Date: 2026-08-27

## Decision

Every policy statement requires at least one `CIT-NNN` identifier from its immutable pack. Unknown
or foreign identifiers fail the run; duplicates normalize in stable order. Pack creation rechecks
tenant, ACTIVE status, and the retrieval run's as-of effective interval.

## Consequences

An LLM cannot introduce another tenant, retrieval run, future/retired version, or non-existent
clause. A semantic mismatch between a valid citation and its sentence still requires model
qualification and is not claimed by this validator.
