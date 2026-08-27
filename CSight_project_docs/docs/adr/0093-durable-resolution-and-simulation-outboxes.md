# ADR-0093: Resolution and Simulation use distinct durable outboxes

- Status: Accepted
- Date: 2026-08-27

## Decision

`case_resolution.requested.v1` and `external_action.simulation_requested.v1` use separate durable
outboxes with claim tokens, leases, bounded publish backoff, terminal failure records, exact-event
consumption, and identifier-only queue payloads.

## Consequences

Broker-confirm crashes may cause duplicate delivery, so consumers are idempotent and fenced by
database identity. Mapping and simulation failures remain separately recoverable and auditable.
