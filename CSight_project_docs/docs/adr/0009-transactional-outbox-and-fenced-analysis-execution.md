# ADR-0009: Transactional Outbox와 Fenced Analysis 실행

- 상태: Accepted
- 일자: 2026-08-26

## Context

Analysis Run 등록 뒤 API가 직접 Celery 메시지를 발행하면 DB Commit과 Broker Publish 사이에
원자성이 없다. DB만 성공하면 작업이 영구 대기하고, Broker만 성공하거나 Publisher가 확인
직후 종료되면 중복 전달될 수 있다. `acks_late` Worker도 Provider 호출 중 종료될 수 있으므로
At-least-once 전달을 정상 상황으로 취급해야 한다.

## Decision

- Analysis Run, `TEXT_EXTRACTION` Stage, 분석 요청 Idempotency Record와
  `analysis.requested.v1` Outbox Event를 하나의 PostgreSQL Transaction으로 저장한다.
- 별도 Dispatcher가 `PENDING` Event를 `FOR UPDATE SKIP LOCKED`로 Claim하고, Commit 뒤
  RabbitMQ에 발행한 다음 Claim Token이 일치할 때만 `PUBLISHED`로 완료한다.
- Publish 실패는 지수 Backoff와 제한된 Jitter를 적용해 다시 `PENDING`으로 돌린다. 최대
  횟수 소진 시 Event와 아직 시작하지 못한 Run·Stage를 `OUTBOX_DISPATCH_FAILED`로 끝낸다.
- 오래된 `PROCESSING` Claim은 Lease 만료 후 회수한다. Publisher Confirm 뒤 Process가
  종료되는 경우의 중복 발행은 허용한다.
- Queue Payload는 `event_id`, `tenant_id`, `case_id`, `analysis_run_id`, `stage_run_id`,
  `correlation_id` 여섯 식별자만 포함한다. Worker가 PostgreSQL에서 현재 입력을 다시 읽는다.
- Worker는 Stage Claim Token과 Lease를 사용한다. Provider 호출은 DB Transaction 밖에서
  실행하고, 결과 저장과 Attempt·Stage·Run 완료는 같은 Token이 여전히 유효할 때만 한
  Transaction으로 Commit한다.
- Worker Lost와 Hard Timeout은 Late Acknowledgment Delivery를 재큐잉한다. 여섯 ID Payload
  검증 뒤 발생한 일반 인프라 예외와 Soft Timeout도 명시적 `Reject(requeue=True)`로 바꾼다.
  Schema가 잘못된 Poison Message는 이 경계 밖에서 거부해 무한 재큐잉하지 않는다.
- 활성 Lease 중복 전달은 Lease 만료 시각의 참조 전용 Outbox Wake-up을 Commit하고 No-op
  처리한다. 최종 허용 Attempt의 Lease가 만료되면 새 Attempt를 만들지 않고 Stage·Attempt·Run을
  Claim Token으로 Fencing한 한 Transaction에서 실패로 종결한다.
- Transient Provider 실패는 `RETRY_WAITING`과 다음 Outbox Event를 같은 Transaction으로
  저장한다. Celery 자체 Retry를 상태의 Source of Truth로 사용하지 않는다.

## Consequences

### 장점

- API 성공 뒤 Broker 장애가 발생해도 작업 등록을 잃지 않는다.
- 중복 Publish, 중복 Delivery와 이전 Worker의 늦은 응답이 결과를 덮어쓰지 못한다.
- 재시도 상태와 다음 전달 요청이 DB에서 함께 복구된다.
- Worker 재전달이 기존 활성 Lease보다 먼저 도착해도 Run이 `RUNNING`에 영구 고립되지 않는다.

### 비용과 제한

- Dispatcher, Claim Lease, Attempt 이력과 복구 운영이 추가된다.
- Exactly-once Publish를 제공하지 않는다. Worker 멱등성과 DB Unique Constraint가 필수다.
- 활성 Lease에서 처리한 중복 Delivery마다 미래 Wake-up Event가 추가될 수 있다. 정상 Worker가
  먼저 완료하면 해당 Event는 Terminal No-op이 된다.
- RabbitMQ DLQ와 운영자용 수동 재처리 API는 Sprint 2 범위가 아니다.

## Guardrails

- Outbox와 Queue Payload에 고객 원문, Prompt, Raw Provider Response, JWT, Signed URL 또는
  Secret을 넣지 않는다.
- Result Repository는 Update/Delete를 노출하지 않으며 성공 결과의 DB Unique Constraint를
  유지한다.
- 외부 Provider 호출 중 DB Transaction이나 Row Lock을 유지하지 않는다.
