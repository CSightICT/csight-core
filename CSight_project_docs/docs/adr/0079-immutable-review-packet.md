# ADR-0079: Review packets are immutable

- Status: Accepted
- Date: 2026-08-27

## Decision

Task creation freezes allowlisted case metadata, qualification scopes, analysis and policy
identifiers, citations, effects, and versions into one content-hashed packet per task.

## Consequences

New evidence does not mutate the packet in Sprint 5B. Packet revisioning is deferred.
