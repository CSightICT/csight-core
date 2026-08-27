# ADR-0067: Use typed field and operator registries

- Status: Accepted
- Date: 2026-08-27

## Decision

Policy fields and operators are closed enums with registry version `1.0.0`. Schema validation
checks operator/type compatibility. Arbitrary paths, expressions, SQL, `eval`, and `exec` are
forbidden.

## Consequences

Unknown or incompatible rules fail before persistence or execution.
