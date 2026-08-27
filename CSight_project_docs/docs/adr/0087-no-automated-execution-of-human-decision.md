# ADR-0087: Human decisions do not execute external actions

- Status: Accepted
- Date: 2026-08-27

## Decision

Sprint 5B records decisions only. It does not call payment, refund, exchange, reshipment, CRM,
notification, or report services.

## Consequences

Future execution requires explicit adapters, idempotency, authorization, and separate audit design.
