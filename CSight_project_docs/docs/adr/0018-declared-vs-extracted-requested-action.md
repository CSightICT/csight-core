# ADR-0018: Declared Requested Action과 Extracted Requested Action 분리

- 상태: Accepted
- 일자: 2026-08-26

## Context

Case UI/API 선택값과 고객 자유 텍스트에서 명시된 요청을 하나의 값으로 평가해 의미가 혼합됐다.

## Decision

`case.requested_action`은 declared 값으로 보존하고 LLM v2는 텍스트에 실제 등장한 요청만
`requested_actions[]`와 exact quote로 반환한다. 요청이 없으면 빈 배열이며 `UNSPECIFIED` item을
만들지 않는다. 두 값의 관계는 Application rule `1.0.0`이 결정한다.

## Consequences

복수 요청과 입력 불일치를 측정할 수 있고 LLM 추론을 업무 입력처럼 오인하지 않는다.
