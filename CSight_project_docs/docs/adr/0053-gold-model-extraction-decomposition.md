# ADR-0053: Gold and model extraction are reported separately

- Status: Accepted
- Date: 2026-08-27

## Decision

Gold Extraction measures query-builder/retriever upper bounds. Model Extraction measures end-to-end
quality only when the pinned external Qwen endpoint is actually available.

## Consequences

Mock output is never reported as Qwen performance and extraction errors are not hidden.
