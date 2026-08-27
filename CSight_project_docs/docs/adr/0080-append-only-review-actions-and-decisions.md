# ADR-0080: Review actions and final decisions are append-only

- Status: Accepted
- Date: 2026-08-27

## Decision

Every accepted transition writes one action. A task has at most one immutable decision and its
validated basis rows; repositories expose no update, delete, or overwrite operation.

## Consequences

Correction and amendment require a future versioned workflow, not mutation.
