# ADR-0066: Policy rules are immutable and versioned

- Status: Accepted
- Date: 2026-08-27

## Decision

Identify a rule set by tenant, name, and version and reject a content-hash conflict. Changes create
a new version and activation record; stored rules are not overwritten.

## Consequences

Historical evaluations retain the exact rule-set hash and remain reproducible.
