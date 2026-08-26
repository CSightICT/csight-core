# ADR-0036: Retrieval Does Not Make Policy Decisions

- 상태: Accepted
- 일자: 2026-08-26

## Decision

검색 API는 관련 policy clause와 retrieval metadata만 반환한다. 적용 여부, 승인·거절, 환불·교환,
사기·책임 판단을 생성하지 않는다.

## Consequences

정책 version과 사람 검토가 최종 결정을 소유한다. 검색 hit는 근거 후보이지 판정이 아니다.
