# ADR-0002: LLM과 Vision을 독립 Inference Node로 분리

- 상태: Accepted
- 일자: 2026-08-25

## Context

LLM과 Vision은 서로 다른 GPU 서버에서 실행될 예정이며, 모델 생명주기와 확장 방식이 Core Backend와 다르다.

## Decision

- LLM은 별도 Node에서 vLLM으로 서빙한다.
- Vision은 별도 Node에서 초기 FastAPI, 안정화 후 Triton을 검토한다.
- 두 Node는 Stateless로 운영한다.
- 두 Node는 업무 DB에 직접 접근하지 않는다.
- Core Worker만 사설망을 통해 호출한다.

## Consequences

- 모델 교체와 장애가 Core 상태에 직접 영향을 주지 않는다.
- 네트워크 Timeout과 부분 실패를 명시적으로 처리해야 한다.
- API Contract와 Health Check가 중요해진다.
