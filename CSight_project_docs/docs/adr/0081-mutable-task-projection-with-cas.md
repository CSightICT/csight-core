# ADR-0081: Mutable review-task projection uses CAS

- Status: Accepted
- Date: 2026-08-27

## Decision

Queue state is a mutable projection protected by an expected version and row lock. The action,
assignment change, and projection change share one transaction.

## Consequences

Concurrent claims yield one success and one conflict, with no partial state.
