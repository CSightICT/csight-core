# ADR-0084: Final-decision basis is allowlisted

- Status: Accepted
- Date: 2026-08-27

## Decision

Decision basis may reference only packet-scoped policy rule results, citations, frozen analysis
evidence, or the extraction result. Approval and rejection require policy basis.

## Consequences

Unknown, cross-run, or cross-tenant references fail closed before any decision row is written.
