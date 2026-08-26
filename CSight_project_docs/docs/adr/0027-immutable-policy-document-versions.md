# ADR-0027: Immutable Policy Document Versions

- 상태: Accepted
- 일자: 2026-08-26

## Decision

`tenant_id, document_id, document_version`은 불변 식별자다. 동일 버전의 source hash가 다르면
`POLICY_DOCUMENT_VERSION_CONTENT_MISMATCH`로 거부하며 새 의미는 새 version row로 추가한다.

## Consequences

기존 정책을 update/hard-delete하지 않고 분석 재현성과 감사 가능성을 보존한다.
