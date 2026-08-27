# ADR-0095: A conflicting Human Decision requires manual follow-up

- Status: Accepted
- Date: 2026-08-27

## Decision

An exact Decision-event redelivery is a no-op. A different immutable Human Decision ID for a Case
transitions the Resolution Projection to `MANUAL_FOLLOW_UP_REQUIRED`, records both identities in an
append-only Event, preserves all earlier artifacts, and creates no new Action Intent.

## Consequences

Sprint 5C never selects a winner or silently supersedes a Decision. Decision amendment, correction,
reopen, and automatic reconciliation remain deferred.
