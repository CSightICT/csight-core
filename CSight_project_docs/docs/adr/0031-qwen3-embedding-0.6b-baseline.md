# ADR-0031: Qwen3-Embedding-0.6B Baseline

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Dense baseline은 `Qwen/Qwen3-Embedding-0.6B` revision
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, 1024 dimension, last-token pooling,
L2 normalization을 사용한다. host-native MPS runtime을 Core와 분리한다.

## Consequences

Core는 private HTTP port만 호출하고 모델 runtime은 DB에 접근하지 않는다. 서비스 장애 시 lexical은
계속 동작하고 dense/hybrid만 안전한 503을 반환한다.
