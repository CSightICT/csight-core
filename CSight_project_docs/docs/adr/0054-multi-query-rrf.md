# ADR-0054: Versioned multi-query RRF fusion

- Status: Accepted
- Date: 2026-08-27

## Decision

Fuse per-query HYBRID top-20 results with `policy_multi_query_rrf:1.0.0`, rrf_k 20, equal query
weight, and an identity including tenant, document, document version, and clause.

## Consequences

Ranks are stable and every final hit retains matched query IDs and per-query ranks.
