# ADR-0035: Metadata Filter before Retrieval

- 상태: Accepted
- 일자: 2026-08-26

## Decision

인증 principal tenant, ACTIVE status, as-of effective interval과 allowlisted optional filters를 BM25
candidate 생성 및 dense distance 계산 전에 적용한다.

## Consequences

다른 tenant, retired, future policy는 rank 후 제거되는 것이 아니라 후보에 들어오지 않는다.
