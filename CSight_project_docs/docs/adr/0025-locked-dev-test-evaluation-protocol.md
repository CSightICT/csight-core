# ADR-0025: Locked Dev/Test Evaluation Protocol

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Extraction 120/40, Retrieval 80/40 등 고정 dev/test split과 content hash를 manifest에 기록한다.
Prompt 변경은 dev만 사용하고 Prompt hash freeze 뒤 external test를 한 번만 실행한다. test 결과로
동일 Prompt를 다시 튜닝하지 않는다.

## Consequences

현재 Qwen endpoint가 없으면 실제 평가는 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`이며 reference
self-check를 모델 평가로 표현하지 않는다.
