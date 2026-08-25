# ADR-0005: Celery와 RabbitMQ 기반 비동기 AI 작업

- 상태: Accepted
- 일자: 2026-08-25

## Context

LLM과 Vision 추론은 수초 이상 걸릴 수 있고 외부 GPU 서버 장애에 영향을 받는다. 일반 HTTP 요청 안에서 완료하면 Timeout, 재시도, 작업 유실 문제가 발생한다.

## Decision

- FastAPI는 작업을 등록하고 `202 Accepted`를 반환한다.
- Celery Worker가 LLM·Vision 호출과 결과 결합을 수행한다.
- RabbitMQ를 Broker로 사용한다.
- Idempotency, Retry, Timeout, DLQ, Partial Failure를 지원한다.

## Consequences

- 운영 구성요소가 증가한다.
- 장시간 작업의 복원력과 추적성이 향상된다.
- API Process와 Worker의 공통 Application 코드가 필요하다.
