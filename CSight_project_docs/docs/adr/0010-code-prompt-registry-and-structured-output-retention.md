# ADR-0010: Code Prompt Registry와 구조화 결과만 보존

- 상태: Accepted
- 일자: 2026-08-26

## Context

LLM Prompt를 Router나 Worker에 흩어 놓으면 동작 변경을 추적하기 어렵고, 고객 입력을 문자열
명령으로 연결하면 Prompt Injection 경계가 불명확해진다. Raw Prompt와 Raw Provider
Response를 저장하면 고객 원문·System Prompt·Chain-of-thought 또는 Provider 내부 정보의
불필요한 보존 위험도 생긴다.

## Decision

- Prompt는 immutable `PromptManifest`와 Code-based Registry로 관리한다. Manifest는 이름,
  버전, 입·출력 Schema 버전, System/User Template와 Canonical SHA-256 Content Hash를 가진다.
- 고객 입력은 Allowlist DTO를 JSON으로 Escape해 단 하나의 Untrusted Data Placeholder에
  삽입한다. `attributes`, 내부 ID, JWT, MinIO URL과 이미지 Binary는 전달하지 않는다.
- vLLM에는 Pydantic JSON Schema를 `response_format=json_schema`로 전달하고 Model,
  Temperature, 최대 Output Token을 명시한다.
- Provider 응답은 Strict Pydantic Schema로 검증하며 추가 Field를 거부한다. `source_quote`가
  있으면 원문의 정확한 연속 부분 문자열인지 Application 경계에서 다시 검증한다.
- DB에는 검증된 구조화 결과와 Provider·Model·Prompt·Schema 식별자, Token Usage와 Latency만
  저장한다. 전체 Prompt, Raw Response와 Chain-of-thought는 저장하거나 로그에 남기지 않는다.
- LLM 출력은 문의 내용 구조화만 담당하며 승인·거절·보상·사기·책임·정책 판정을 표현하는
  Field를 제공하지 않는다.

## Consequences

### 장점

- 실행 결과를 Prompt·Schema 버전과 함께 재현·비교할 수 있다.
- Injection 문장은 명령이 아니라 고객 데이터로 남고, 허용되지 않은 출력은 저장 전에
  차단된다.
- Raw 응답 비보존으로 불필요한 개인정보와 Provider 데이터 Retention을 줄인다.

### 비용과 제한

- Prompt 내용이 바뀌면 버전과 Hash를 함께 갱신하고 회귀 평가해야 한다.
- 정확한 Quote 검사는 인용문 일치만 보장한다. Summary의 모든 의미적 환각을 기계적으로
  증명하지는 못한다.
- DB Prompt 편집 UI, 자동 Model 선택과 Fallback Provider는 Sprint 2 범위가 아니다.

## Guardrails

- Output Schema에 확률형 Confidence나 최종 업무 결정을 추가하지 않는다.
- Schema 또는 Prompt의 동작 호환성이 깨지면 Version을 올린다.
- 기본 테스트에서는 결정적 Mock을 사용하고 외부 vLLM 검증은 `external_gpu` Marker로
  명시적으로 분리한다.
