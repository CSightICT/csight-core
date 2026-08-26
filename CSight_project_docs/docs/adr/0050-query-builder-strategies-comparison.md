# ADR-0050: Query-builder strategies and comparison protocol

- Status: Accepted
- Date: 2026-08-27

## Decision

Compare RAW, deterministic 1.0.0, and LLM prompt 1.1.0 with the same corpus, active index, HYBRID
profile, top-K, and hard filters. Tune only on the new Dev 80 split and evaluate sealed Test 40 once.

## Consequences

Strategy selection is attributable to query planning rather than retriever or reranker changes.
