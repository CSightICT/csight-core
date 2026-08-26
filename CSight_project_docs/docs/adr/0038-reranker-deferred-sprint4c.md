# ADR-0038: Reranker Deferred to Sprint 4C

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Sprint 4B baseline에는 Qwen3 reranker/cross-encoder, query builder, grounded generation을 넣지 않는다.

## Consequences

Sprint 4C는 frozen retrieval candidate set 위에서 reranking과 citation grounding을 별도 profile과
locked evaluation으로 검증한다.
