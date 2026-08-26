# ADR-0045: No silent fallback on reranker failure

- Status: Accepted
- Date: 2026-08-26

## Decision

`HYBRID_RERANKED` returns `503 RERANKER_PROVIDER_UNAVAILABLE` when the provider is down. It never
returns a Hybrid ranking under a successful reranked response. Existing modes remain available.

## Consequences

Callers can distinguish ranking provenance. Core readiness remains independent of optional model
availability.
