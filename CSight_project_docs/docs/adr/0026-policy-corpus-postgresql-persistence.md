# ADR-0026: Policy Corpus PostgreSQL Persistence

- 상태: Accepted
- 일자: 2026-08-26

## Decision

검증된 normalized document/clause JSONL을 PostgreSQL의 명시적 관계형 컬럼에 적재한다. Raw
Markdown과 임의 JSONB는 검색 원본이 아니며 embedding 생성은 ingestion transaction과 분리한다.

## Consequences

Tenant·status·effective date filter를 SQL에서 선적용하고 corpus 무결성을 FK와 unique constraint로
검증할 수 있다. 합성 corpus는 local/test에서 명시적 CLI로만 적재한다.
