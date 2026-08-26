# ADR-0056: No silent query-builder fallback

- Status: Accepted
- Date: 2026-08-27

## Decision

LLM unavailability, timeout, or invalid structured output fails the LLM run with a stable error code.
It never returns deterministic output under the LLM strategy.

## Consequences

Fallback would require a separately named and versioned future profile.
