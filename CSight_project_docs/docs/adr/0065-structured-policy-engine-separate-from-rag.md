# ADR-0065: Structured Policy Engine is separate from RAG

- Status: Accepted
- Date: 2026-08-27

## Decision

Retrieval finds clauses, grounded generation explains selected clauses, and the Policy Engine
executes only curated structured rules. Retrieval hits and generated text are never executable
policy inputs.

## Consequences

Rule behavior is reviewable and deterministic; RAG cannot silently create policy decisions.
