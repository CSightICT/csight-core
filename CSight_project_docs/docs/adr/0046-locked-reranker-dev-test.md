# ADR-0046: Locked Dev/Test reranker evaluation

- Status: Accepted
- Date: 2026-08-26

## Decision

Select candidate K, instruction, serialization, token limits and batch only on Dev 80; freeze their
hashes; call Test 40 once. Test results cannot trigger profile changes.

## Consequences

The no-gain result is retained without post-hoc tuning. Dev may be rerun only for deterministic
verification; Test is not rerun.
