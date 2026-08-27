# ADR-0094: Sprint 5C External Action is DRY-RUN only

- Status: Accepted
- Date: 2026-08-27

## Decision

The Sprint 5C adapter is deterministic, network-free, and accepts production Intents only in
`DRY_RUN`. `LIVE` always fails with `LIVE_EXTERNAL_ACTION_DISABLED`. Every Result records
`side_effects_performed = false`.

## Consequences

No payment, refund, exchange, reshipment, repair, CRM, notification, or customer communication is
performed. `ACTION_DRY_RUN_VALIDATED` asserts contract validation, not business execution.
