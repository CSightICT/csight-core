# ADR-0023: Policy Document와 Clause 버전 관리

- 상태: Accepted
- 일자: 2026-08-26

## Decision

Document는 tenant/document/version, effective dates, ACTIVE/RETIRED와 supersedes 관계를 가진다.
Clause ID는 `document_id:document_version:local_clause`로 안정 생성한다. Resolver는 tenant와
as-of date에서 ACTIVE이며 유효한 최신 semantic version만 선택한다.

## Consequences

Retired/future/cross-tenant 문서를 Gold에서 명시적으로 배제할 수 있다.
