# ADR-0070: Freeze a policy evaluation input snapshot

- Status: Accepted
- Date: 2026-08-27

## Decision

Create one content-hashed typed input and qualification snapshot with each evaluation run. Store
source result identifiers, not a duplicate of the customer message or raw provider payload.

## Consequences

Worker retries use identical inputs while sensitive-data duplication remains bounded.
