# ADR-0074: Mock Vision produces NOT_EVALUATED

- Status: Accepted
- Date: 2026-08-27

## Decision

Conditions needing detected Vision defects return `NOT_EVALUATED` unless the source is
`PRODUCTION_QUALIFIED`. A mock result may not establish an automatic policy fact.

## Consequences

Vision-dependent rules remain indeterminate and require human review until real qualification.
