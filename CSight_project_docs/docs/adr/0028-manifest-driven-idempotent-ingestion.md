# ADR-0028: Manifest-driven Idempotent Ingestion

- 상태: Accepted
- 일자: 2026-08-26

## Decision

manifest hash, corpus source hash, builder version이 같은 성공 run을 재사용한다. 적재 전 hash/count,
적재 후 parent/tenant/version 관계와 count를 검증한다.

## Consequences

반복 실행은 document/clause 중복을 만들지 않는다. 잘못된 manifest나 content mismatch는 적재를
중단하며 기존 성공 데이터는 유지한다.
