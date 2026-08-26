# ADR-0051: Core owns hard policy filters

- Status: Accepted
- Date: 2026-08-27

## Decision

Core supplies tenant, ACTIVE status, and as-of date. Product category is hard only when it comes from
trusted Case metadata. LLM policy, defect, and clause-type hints remain validated soft metadata.

## Consequences

An LLM cannot broaden tenancy or select future, retired, or arbitrary document versions.
