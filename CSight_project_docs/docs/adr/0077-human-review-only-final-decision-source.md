# ADR-0077: Human Review is the only final-decision source

- Status: Accepted
- Date: 2026-08-27

## Decision

Only an authenticated `ADMIN` or `REVIEWER` may create a final decision, through the explicit
resolve use case. Policy, LLM, Vision, RAG, outbox, and Celery code cannot create decision rows.

## Consequences

Workers create only tasks, packets, and `CREATED` actions. Architecture tests guard this boundary.
