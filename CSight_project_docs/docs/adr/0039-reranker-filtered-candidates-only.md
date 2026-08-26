# ADR-0039: Reranker operates only on filtered candidates

- Status: Accepted
- Date: 2026-08-26

## Decision

Core applies tenant, ACTIVE status, effective-date, version and allowlisted metadata filters before
serialization. The reranker receives only candidate ID and passage text and has no database access.

## Consequences

The model cannot add an out-of-scope policy. Candidate allowlist validation fails closed on any set
mutation, at the cost of keeping filter ownership in Core.
