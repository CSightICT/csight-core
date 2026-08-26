# ADR-0022: Clause 중심 정책 분할

- 상태: Accepted
- 일자: 2026-08-26

## Decision

정책을 고정 문자 길이로 자르지 않고 Markdown heading 아래의 명시적 Clause 단위로 정규화한다.
Rule·Exception·Evidence Requirement·Escalation·Definition·Procedure type과 section path를
보존하며 Exception은 `parent_clause_id`로 원 Rule에 연결한다.

## Consequences

검색 결과가 예외만 고립시켜 의미를 왜곡하는 위험을 평가할 수 있다.
