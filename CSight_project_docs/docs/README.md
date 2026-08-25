# CSight Documentation Index

| 번호 | 문서 | 목적 |
|---:|---|---|
| 01 | [Project Charter](01_PROJECT_CHARTER.md) | 제품 가설과 범위 |
| 02 | [Product Requirements](02_PRODUCT_REQUIREMENTS.md) | 기능·비기능 요구사항 |
| 03 | [Architecture](03_ARCHITECTURE.md) | 배포·논리 구조 |
| 04 | [Domain Model and Workflow](04_DOMAIN_MODEL_AND_WORKFLOW.md) | 상태·규칙·용어 |
| 05 | [API and Event Contracts](05_API_AND_EVENT_CONTRACTS.md) | 통합 계약 |
| 06 | [Data and ML Plan](06_DATA_AND_ML_PLAN.md) | 데이터·모델·RAG |
| 07 | [Database Design](07_DATABASE_DESIGN.md) | 저장과 버전 관리 |
| 08 | [Security and Operations](08_SECURITY_AND_OPERATIONS.md) | 보안·운영 |
| 09 | [Testing and Evaluation](09_TESTING_AND_EVALUATION.md) | 테스트·KPI |
| 10 | [Roadmap and Backlog](10_ROADMAP_AND_BACKLOG.md) | Sprint 실행 계획 |
| 11 | [Mentoring Decision Log](11_MENTORING_DECISION_LOG.md) | 멘토링 결과 관리 |
| ADR | [Architecture Decisions](adr/) | 확정된 설계 결정 |

## Sprint 1 Accepted ADR

- [ADR-0006](adr/0006-principal-derived-tenant-and-local-jwt.md): 인증 Principal 기반
  Tenant 경계와 로컬 JWT
- [ADR-0007](adr/0007-private-evidence-storage-and-compensation.md): Private Evidence 저장,
  내부/Presign Endpoint와 최선 노력 보상
- [ADR-0008](adr/0008-case-create-idempotency.md): Tenant 단위 Case 생성 Idempotency
