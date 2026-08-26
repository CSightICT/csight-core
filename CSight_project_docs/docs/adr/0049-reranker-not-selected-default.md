# ADR-0049: Reranker is not the default retrieval path

- Status: Accepted
- Date: 2026-08-27

## Decision

Keep frozen HYBRID retrieval as the default. HYBRID_RERANKED remains an explicit experiment because
Sprint 4C-1 Test MRR@10 fell from 0.53833 to 0.51250 and nDCG@10 from 0.59841 to 0.59802.

## Consequences

Query-builder evaluation cannot enable the reranker, so its effect stays independently measurable.
