# ADR-0041: Measure oracle upper bound before reranker qualification

- Status: Accepted
- Date: 2026-08-26

## Decision

For K 10/20/30/50, place candidate-contained Gold clauses first only as an offline diagnostic and
report oracle Recall, MRR, nDCG and exact coverage. Never expose oracle as retrieval performance.

## Consequences

Candidate absence is separated from ordering loss. K=20 is the smallest Dev K reaching maximum
candidate recall; K=30/50 add no coverage.
