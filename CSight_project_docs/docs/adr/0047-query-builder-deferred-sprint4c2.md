# ADR-0047: Defer Policy Query Builder to Sprint 4C-2

- Status: Accepted
- Date: 2026-08-26

## Decision

Sprint 4C-1 reranks the existing raw-query candidate stream only. Deterministic and LLM-generated
structured query variants are a separate locked evaluation in Sprint 4C-2.

## Consequences

Query formulation effects cannot be confused with cross-encoder ranking effects.
