# ADR-0011: Case와 Analysis Run 수명주기 분리

- 상태: Accepted
- 일자: 2026-08-26

## Context

Case는 고객 문의 접수와 상담 업무의 수명주기이고, AI 분석은 재시도·실패·재분석이 가능한
별도 실행이다. Provider 장애를 Case 상태에 반영하면 접수된 Case가 사라지거나 업무 상태와
기술 상태가 혼합되고, 같은 Case를 다른 Model·Prompt로 재분석하기 어렵다.

## Decision

- Sprint 2 분석 요청은 기존 Case 상태를 변경하지 않는다.
- 각 요청은 새 immutable-identity `AnalysisRun`과 Pipeline Stage Run을 생성한다.
- Run과 Stage는 `QUEUED`, `RUNNING`, `RETRY_WAITING`, `SUCCEEDED`, `FAILED`를 사용하고
  명시적으로 허용된 전이만 Domain에서 허용한다. Terminal 상태에서의 전이는 금지한다.
- 각 Provider 시도는 `analysis_stage_attempts`에 별도 이력으로 남긴다. 성공한 Text
  Extraction Result는 Run·Stage당 최대 하나이며 Update/Delete 경로를 제공하지 않는다.
- Case 상세는 편의를 위해 최신 Run의 안전한 요약을 조회하지만 Case Entity에 분석 상태를
  복제하지 않는다.
- 재분석은 기존 Run을 되살리거나 덮어쓰지 않고 새 Run을 등록한다.

## Consequences

- Case 접수 가용성이 외부 LLM 상태와 분리된다.
- 재시도와 재분석을 구분하고 실행별 Model·Prompt·Schema Snapshot을 감사할 수 있다.
- 조회 시 Case와 최신 Analysis Run을 조합해야 하며 저장 Row 수가 증가한다.

## Guardrails

- Analysis 실패를 이유로 Case 상태를 자동 변경하지 않는다.
- 성공 Result를 수정하는 Repository API나 일반적인 `retry terminal run` API를 추가하지
  않는다.
- Vision, Alignment, Policy, Routing, Review와 Report는 각각 후속 Stage로 연결하고 Sprint 2
  Text Extraction 성공 여부가 최종 업무 결정을 의미하지 않게 한다.
