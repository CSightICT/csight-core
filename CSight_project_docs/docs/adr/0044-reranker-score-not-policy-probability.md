# ADR-0044: Reranker score is not policy probability

- Status: Accepted
- Date: 2026-08-26

## Decision

`rerank_score` is only the official yes/no-label-normalized pairwise relevance score in `[0,1]`.
It is not calibrated probability, policy applicability, approval likelihood, legal suitability or
business confidence.

## Consequences

Ranking may use the score; policy engines and human reviewers must not interpret it as a decision.
