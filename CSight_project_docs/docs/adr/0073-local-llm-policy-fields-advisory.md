# ADR-0073: Local LLM policy fields are advisory

- Status: Accepted
- Date: 2026-08-27

## Decision

Local extracted requested actions and text ambiguities are not v1 hard fields. Rules using issue
types or claim counts must require human review and prohibit final decisions.

## Consequences

The weak Local action and ambiguity scores cannot control automatic eligibility.
