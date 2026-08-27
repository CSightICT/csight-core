# ADR-0082: Human-review task type and priority mapping is versioned

- Status: Accepted
- Date: 2026-08-27

## Decision

The mapping version is `1.0.0`. Precedence is safety, manager, policy exception, evidence, then
standard. Priority is operational ordering and never a business decision.

## Consequences

Changing meaning requires a new mapping version. Safety is reserved for explicitly classified
safety work and is not inferred from arbitrary model text.
