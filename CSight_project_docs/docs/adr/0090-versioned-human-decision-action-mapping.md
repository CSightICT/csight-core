# ADR-0090: Human Decision to External Action mapping is versioned and deterministic

- Status: Accepted
- Date: 2026-08-27

## Decision

`human_decision_to_external_action/1.0.0` maps the four approval Decisions to `REFUND`, `EXCHANGE`,
`RESHIPMENT`, and `REPAIR`. `REJECT_REQUEST` and `NO_ACTION` map to `ACTION_NOT_REQUIRED`;
`PROVIDE_INFORMATION` maps to `MANUAL_FOLLOW_UP_REQUIRED`.

## Consequences

Unknown Decision types or mapping versions fail closed. Model output, policy effects, rationale, and
customer requested action cannot alter the mapping.
