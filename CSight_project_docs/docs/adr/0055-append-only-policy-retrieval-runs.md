# ADR-0055: Append-only policy retrieval runs

- Status: Accepted
- Date: 2026-08-27

## Decision

Every strategy creates a QUEUED run and transactional outbox event, then records generated queries
and clause-FK hits before a terminal status. Raw customer text is referenced from Case, not copied.

## Consequences

Replays return the same run and duplicate tasks cannot create a second query plan or hit set.
