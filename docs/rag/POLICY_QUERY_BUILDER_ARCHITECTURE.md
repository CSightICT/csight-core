# Policy Query Builder Architecture

Sprint 4C-2 converts one successful Text Extraction v2 result into a decision-free policy search
plan. The platform contract is strict, technology-neutral, and limited to one through three unique
queries. Allowed purposes are primary policy, evidence, exception, escalation, definition, and
procedure.

## Ownership and flow

`POST Case retrieval run → Run + Outbox → policy-retrieval Worker → Query Plan → per-query frozen
HYBRID top-20 → policy_multi_query_rrf:1.0.0 → clause-FK Hits → terminal Run`.

Core owns tenant, ACTIVE status, and as-of date. Trusted Case product category is the only additional
hard filter. Policy, defect, and clause-type hints are allowlisted soft metadata and are not applied
as hard filters in profile 1.0.0. The reranker is disabled.

RAW references the Case message without copying it to the query table. Deterministic uses immutable
`deterministic_policy_query:1.0.0`. LLM uses the existing provider port and immutable
`policy_query_builder:1.1.0`; it receives structured v2 facts, completeness, trusted metadata, and
untrusted source quotes, but not the complete customer message.

Messages contain only event, tenant, Case, retrieval-run, and correlation IDs. Logs may contain
query hashes and counts, never customer text, prompts, raw responses, reasoning, clause text, tokens,
keys, or vectors. LLM and embedding failures are terminal/retryable errors without silent fallback.
