# ADR-0029: Exact BM25 Lexical Baseline

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Robertson BM25 공식을 직접 계산하는 결정론적 lexical baseline을 사용한다. PostgreSQL `ts_rank`를
BM25로 부르지 않으며 dev 80건에서 `k1=1.2`, `b=0.75`를 freeze했다.

## Consequences

점수와 tie-breaker를 fixture로 검증할 수 있고 작은 168-clause corpus에서 재현 가능한 기준선을
제공한다.
