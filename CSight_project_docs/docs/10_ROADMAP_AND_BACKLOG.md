# 10. Roadmap and Backlog

## 1. 개발 방식

- 2주 단위 Sprint
- 각 Sprint는 실행 가능한 Increment를 남긴다.
- 세부 범위는 멘토링과 데이터 확보 결과에 따라 조정한다.
- 기술 구현과 고객·데이터 검증을 병렬로 진행한다.

## 2. Sprint 계획

### Sprint 0 — Foundation

목표: 개발 기반과 계약 확정

- 저장소와 디렉터리 구조
- `pyproject.toml`, Ruff, Type Check, pytest
- Docker Compose Core 환경
- PostgreSQL, RabbitMQ, MinIO
- Alembic 초기 Migration
- LLM·Vision Mock Adapter
- CI Pipeline
- ADR 확정

완료 기준:

- Core 서비스가 한 명령으로 실행
- Health Check 통과
- Mock 기반 E2E Skeleton 통과

### Sprint 1 — Case and Evidence

- Case CRUD
- Evidence 업로드
- MinIO 저장
- 상태 이력
- 기본 인증과 Tenant Scope
- 상담원 Case 목록·상세 API

완료 기준:

- 텍스트와 이미지가 포함된 Case 접수 가능
- 원본 파일이 DB가 아닌 Object Storage에 저장

### Sprint 2 — Async Analysis and LLM

- Celery + RabbitMQ
- Analysis Run
- vLLM Adapter
- 문의 구조화 Schema
- Retry, Timeout, Idempotency
- Prompt Version

완료 기준:

- API가 202 응답 후 LLM 구조화 결과를 비동기로 저장
- 실패와 재시도 이력 확인 가능

### Sprint 3 — Vision Integration

- Vision Contract 확정
- Mock → 실제 Vision API 전환
- 이미지 품질 결과
- Detection 정규화
- Model Version 저장
- LLM·Vision 병렬 실행

완료 기준:

- Vision 모델 교체가 Domain 코드 수정 없이 가능
- 부분 실패 상태가 정상 저장

### Sprint 4 — Alignment, Policy, Review

- Alignment v1
- Policy Version과 Rule Evaluator
- Routing Decision
- 상담원 승인·수정·이관
- Audit Log

완료 기준:

- 명확·모호·자료부족·고위험 Case가 다른 경로로 분기
- AI 권고와 최종 판단 모두 보존

### Sprint 5 — RAG, Report, Evaluation

- 정책 문서 수집·Chunking
- pgvector 검색
- 근거 조항 연결
- 검토 보고서
- KPI 수집
- Offline Evaluation Dataset

완료 기준:

- Case 단위 보고서 생성
- 모델·정책·프롬프트 버전으로 결과 재현 가능
- 핵심 KPI 산출 가능

### Sprint 6 — Shadow Mode and Mentoring PoC

- Shadow Mode UI 또는 Export
- 상담원 판단 비교
- Override Reason 분석
- 오류 Taxonomy
- ROI Baseline 입력
- 멘토 피드백 반영

완료 기준:

- 실제 또는 시뮬레이션 Case로 End-to-End 평가 리포트 생성

## 3. P0 Backlog

- [ ] 프로젝트 Skeleton과 CI
- [ ] Case / Evidence Domain
- [ ] PostgreSQL / Alembic
- [ ] MinIO Upload
- [ ] Celery / RabbitMQ
- [ ] LLM Structured Output
- [ ] Vision Contract와 Adapter
- [ ] Analysis Run / Versioning
- [ ] Alignment v1
- [ ] Policy Evaluator
- [ ] Routing Decision
- [ ] Human Review
- [ ] Audit Log
- [ ] E2E Test

## 4. P1 Backlog

- [ ] 정책 문서 RAG
- [ ] Report Export
- [ ] SSE 상태 알림
- [ ] Dashboard용 집계 API
- [ ] 재촬영 가이드
- [ ] Prompt 관리 UI
- [ ] 모델 비교 재분석
- [ ] Tenant별 Threshold
- [ ] Shadow Mode 비교 화면

## 5. P2 Backlog

- [ ] OIDC / SSO
- [ ] PostgreSQL RLS
- [ ] Triton 전환
- [ ] Object Storage Lifecycle 자동화
- [ ] 외부 CRM Connector
- [ ] OpenTelemetry 기반 분산 Trace
- [ ] Cloud / Linux Core 배포
- [ ] Domain Module 추가

## 6. 병렬 사업 검증 Backlog

- [ ] 초기 고객군 인터뷰 대상 5곳 선정
- [ ] CS 업무 담당자 인터뷰 질문 확정
- [ ] 월간 이미지 문의량 Baseline 조사
- [ ] 평균 검토시간과 재검토율 조사
- [ ] 데이터 제공 가능 범위 확인
- [ ] CRM/API 연동 가능성 확인
- [ ] PoC 성공 기준 합의
- [ ] 구축비·구독·건당 과금 가설 비교

## 7. 역할 분담

### 차인택

- FastAPI Backend
- Domain / Application / Adapter 구조
- PostgreSQL / pgvector
- RabbitMQ / Celery / MinIO
- RAG
- vLLM 배포와 연동
- Vision API 통합
- 전체 Integration / Observability

### Vision 담당자

- 상품군과 결함 Taxonomy 협의
- 데이터 수집·라벨링
- Vision 모델 학습·평가
- Export와 전처리·후처리 명세
- Class별 Threshold와 실패 사례 제공

### 공동

- 고객 가설
- PoC 범위
- 정책 데이터
- 평가 Case
- 멘토링 자료

## 8. Definition of Done

- 기능 요구사항 충족
- 테스트와 Type Check 통과
- Migration 포함
- API·Event Contract 문서화
- 실패·재시도·로그 처리
- 개인정보 영향 검토
- 모델·프롬프트·정책 버전 기록
- Demo Scenario 실행 가능
