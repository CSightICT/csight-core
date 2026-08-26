# ADR-0057: New sealed query-builder holdout

- Status: Accepted
- Date: 2026-08-27

## Decision

Use `policy_query_builder_v1` Dev 80/Test 40. Its Test split is sealed after reference, tenant,
active-version, legacy-text overlap, count, and stable-hash validation.

## Consequences

The previously observed `policy_retrieval_v1` Test remains regression-only.
