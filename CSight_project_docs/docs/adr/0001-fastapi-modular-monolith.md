# ADR-0001: FastAPI 기반 모듈러 모놀리스 채택

- 상태: Accepted
- 일자: 2026-08-25

## Context

팀은 AI 기능과 업무 Backend를 빠르게 통합해야 한다. LLM, RAG, Vision 연동은 Python 생태계와 밀접하며, 초기 PoC 단계에서 Spring Boot와 Python Service를 함께 운영하면 DTO, 상태, 오류, 배포가 중복된다.

## Decision

업무 Backend와 AI Orchestration을 하나의 Python 코드베이스로 구성한다.

- FastAPI API Process
- Celery Worker Process
- 모듈러 모놀리스
- Hexagonal Architecture에 가까운 Port/Adapter 분리

## Consequences

### 장점

- 개발 언어와 Schema 통일
- 빠른 MVP 개발
- Pydantic을 API·모델 계약에 재사용
- 단일 저장소와 배포 단위

### 비용

- Python Domain 경계를 엄격히 유지해야 함
- 파일 하나에 로직이 집중될 위험
- 상용 단계에서 일부 모듈 분리가 필요할 수 있음

## Guardrails

- Domain에서 FastAPI·SQLAlchemy·Celery 직접 import 금지
- 장시간 작업은 Worker로 분리
- 기능 단위 모듈화
- 실제 문제가 생기기 전 마이크로서비스 분리 금지
