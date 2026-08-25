# ADR-0004: Analysis Run Append-only 및 전체 버전 기록

- 상태: Accepted
- 일자: 2026-08-25

## Context

같은 Case도 모델, Prompt, Policy, Threshold 변경에 따라 결과가 달라질 수 있다. 기존 결과를 덮어쓰면 의사결정 재현과 성능 비교가 불가능하다.

## Decision

- 재분석은 새 `analysis_run`을 생성한다.
- 기존 Run과 결과를 삭제·갱신하지 않는다.
- 다음 버전을 필수 기록한다.
  - LLM model
  - Vision model
  - Prompt
  - Policy
  - Threshold
  - Embedding model
  - Retrieval index

## Consequences

- 저장공간 사용량이 증가한다.
- 감사, 비교 평가, 회귀 분석이 가능하다.
- 데이터 보관기간과 삭제 정책을 별도로 설계해야 한다.
