# ADR-0033: Exact pgvector Search before ANN

- 상태: Accepted
- 일자: 2026-08-26

## Decision

168-clause baseline은 ANN index 없이 pgvector cosine distance의 exact ordering을 사용한다. API의
`dense_score`는 `1 - cosine_distance`인 cosine similarity다.

## Consequences

근사 검색 recall 변수를 제거한다. 규모·latency 근거가 생기기 전 HNSW는 추가하지 않는다.
