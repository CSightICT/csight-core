# ADR-0034: RRF Hybrid Fusion

- 상태: Accepted
- 일자: 2026-08-26

## Decision

BM25와 cosine raw score를 더하지 않고 `policy_rrf:1.0.0`을 사용한다. Dev에서 `k=20`, lexical
weight `1.5`, dense weight `0.5`를 freeze했다.

## Consequences

동일 policy version key는 하나로 merge하고 rank/fusion score를 기록한다. stable immutable key로
tie를 해결한다.
