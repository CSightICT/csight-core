# ADR-0092: Resolution request is atomic and Action Intent is immutable

- Status: Accepted
- Date: 2026-08-27

## Decision

The authenticated resolve transaction stores the Human Decision and exact
`case_resolution.requested.v1` outbox event atomically. A Resolution worker may create one immutable,
typed, content-hashed Action Intent only after exact-event, tenant, Case, Decision-hash, mapping, and
input validation.

## Consequences

A committed Decision cannot lose its Resolution request. A partial or invalid request creates no
Intent. Intent update, deletion, replacement, and generic untyped command payloads are unavailable.
