# ADR-0020: LLM Extraction Schema v2와 하위 호환 영속성

- 상태: Accepted
- 일자: 2026-08-26

## Context

복수 요청과 deterministic completeness를 표현해야 하지만 v1 결과 의미와 API를 바꿀 수 없다.

## Decision

Pipeline/Prompt/Schema `2.0.0/2.0.0/2.0`을 추가한다. v1 table은 수정하지 않고 Migration
`20260826_0005`의 append-only child `llm_extraction_results_v2`에 v2와 completeness를 저장한다.
API는 `extraction_result`와 `extraction_result_v2`를 명시적으로 분리한다.

## Consequences

v1 row와 조회가 유지되고 v2 필드가 명시적 컬럼/JSON array 제약으로 검증된다. 두 결과
Repository 모두 update/delete를 노출하지 않는다.
