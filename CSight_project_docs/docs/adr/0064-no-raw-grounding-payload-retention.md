# ADR-0064: Do not retain raw grounding prompts, responses, or reasoning

- Status: Accepted
- Date: 2026-08-27

## Decision

Persist only validated structured explanations, structural metrics, immutable citation snapshots,
and provider/model/prompt/validator provenance. Do not store or log raw prompts, raw provider
responses, chain-of-thought, tokens, customer text, secrets, or clause text in queue messages.

## Consequences

Auditing uses versioned structured data and hashes while minimizing sensitive and model-internal
retention. Debugging cannot rely on replaying stored raw provider payloads.
