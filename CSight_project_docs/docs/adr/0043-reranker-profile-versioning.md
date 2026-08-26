# ADR-0043: Version reranker and execution profiles

- Status: Accepted
- Date: 2026-08-26

## Decision

Persist immutable model, revision, instruction/template hashes, token budgets, K values, batch,
device and score semantics in `policy_reranker_profiles`; bind them to a base index through
`policy_retrieval_execution_profiles`.

## Consequences

The same version cannot change meaning. A failed new qualification cannot retire or alter the
existing Hybrid index.
