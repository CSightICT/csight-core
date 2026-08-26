# ADR-0052: Structured Extraction v2 is query-builder input

- Status: Accepted
- Date: 2026-08-27

## Decision

LLM and deterministic builders consume Extraction v2, backend completeness, and trusted metadata.
The LLM path does not receive the complete customer message; exact source quotes remain untrusted.

## Consequences

Query planning does not become a second unrestricted extraction or decision stage.
