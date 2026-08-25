# ADR-0008: Tenant 단위 Case 생성 Idempotency 영속화

- 상태: Accepted
- 일자: 2026-08-26

## Context

상담원 Client나 Proxy가 Timeout 후 Case 생성 요청을 재시도하면 같은 문의가 중복 저장될
수 있다. 메모리 Cache만으로는 API 재시작과 다중 Replica에 대응할 수 없으며, 요청 확인과
Case 생성 사이의 Race Condition도 막지 못한다. 동시에 같은 문자열의 Key를 서로 다른
Tenant가 독립적으로 사용할 수 있어야 한다.

## Decision

- `POST /api/v1/cases`는 선택적 `Idempotency-Key` Header를 지원한다.
- 영속 레코드의 고유 범위는 `(tenant_id, operation, idempotency_key)`이며 Sprint 1의
  Operation은 `case.create.v1`이다.
- Hash 입력은 `tenant_id`와 Header를 제외한 검증·정규화된 Case 생성 Body다. JSON Key를
  정렬하고 공백 없는 UTF-8 JSON으로 직렬화한 뒤 SHA-256을 계산한다. 유한하지 않은 숫자는
  허용하지 않는다.
- PostgreSQL의 Unique Constraint와 `INSERT ... ON CONFLICT DO NOTHING`을 사용해 먼저
  Idempotency Claim을 획득한다. Claim과 Case·최초 상태 이력 저장은 하나의 DB
  Transaction으로 Commit한다.
- 동일 Tenant, Operation, Key와 동일 Hash가 이미 있으면 연결된 기존 Case를 반환하며
  HTTP `200 OK`를 사용한다. 새 생성은 `201 Created`다.
- 동일 범위의 Key가 다른 Hash로 재사용되면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다.
- 다른 Tenant의 같은 Key는 별도 범위이므로 독립적으로 처리한다.
- Key가 없으면 일반 Case 생성으로 처리한다.
- 레코드에는 `created_at`과 `expires_at = created_at + 24시간`을 기록한다. Sprint 1에서
  `expires_at`은 향후 Retention/정리 정책을 위한 메타데이터다.

## Consequences

### 장점

- 프로세스 재시작과 동시 요청에도 중복 Case 생성을 DB 수준에서 차단한다.
- 같은 Key에 다른 요청이 섞이는 Client 오류를 명확한 `409`로 드러낸다.
- Tenant 간 Key 충돌 없이 동일 Client 전략을 사용할 수 있다.

### 비용과 제한

- Idempotency 레코드가 추가 저장공간을 사용한다.
- Sprint 1은 만료 레코드 Cleanup Job과 만료 후 Key 재사용을 지원하지 않는다. 따라서
  24시간이 지나도 기존 Unique Row가 있는 한 같은 Key는 기존 결과를 재생하거나 `409`를
  반환한다.
- 저장된 레코드가 가리키는 Case가 비정상적으로 없으면 `500
  INCONSISTENT_PERSISTENCE_STATE`를 반환하며 자동 복구하지 않는다.
- Evidence 업로드 Idempotency는 이 ADR의 범위가 아니며 후속 Sprint로 이관한다.

## Guardrails

- Canonical Hash 규칙을 변경할 때는 Operation 버전을 올리고 호환성을 검토한다.
- Header 최대 길이와 DB 컬럼 길이를 동일하게 유지한다.
- 응답 재생, Payload 충돌, Tenant 격리, 동시 Claim을 테스트한다.
