# ADR-0086: Qualification metadata is visible to reviewers

- Status: Accepted
- Date: 2026-08-27

## Decision

The packet freezes source qualification, including `LOCAL_POC`, `MOCK_QUALIFIED`, and
`NOT_AVAILABLE`, so UI and API consumers cannot mistake confidence scope for factual proof.

## Consequences

Mock Vision is not presented as real-model evidence and Local MLX remains qualified only as a PoC.
