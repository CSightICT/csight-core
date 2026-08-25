# 08. Security and Operations

## 1. 네트워크 경계

```text
외부 사용자
→ HTTPS Web/API
→ Core Application & Data Plane
→ 사설망
→ LLM / Vision Inference Node
```

### 외부 공개

- Reverse Proxy의 HTTPS 포트

### 사설망 전용

- PostgreSQL
- RabbitMQ
- MinIO 관리·API 포트
- vLLM API
- Vision API 또는 Triton

### 차단

- 외부 → DB
- 외부 → LLM / Vision API
- LLM / Vision → 업무 DB

## 2. 인증과 권한

### MVP

- JWT 기반 인증
- 역할: Admin, Reviewer, QualityViewer
- Tenant Scope

### 기업 PoC 이후

- OIDC / SSO
- 세부 Resource 권한
- 관리자 작업 2차 확인
- PostgreSQL RLS 검토

## 3. 개인정보와 민감정보

- 고객 문의와 이미지에는 이름, 연락처, 주소, 주문정보가 포함될 수 있다.
- 로그에 고객 원문 전체를 남기지 않는다.
- Object Storage 접근은 짧은 만료시간의 Signed URL을 사용한다.
- 개발 데이터는 마스킹 또는 합성 데이터를 우선한다.
- 원본과 파생 데이터의 보관기간을 분리한다.
- 삭제 요청 시 Vector Index와 보고서 파생본까지 범위를 정의한다.

## 4. Secret 관리

- `.env`를 저장소에 Commit하지 않는다.
- `.env.example`에는 키 이름만 제공한다.
- vLLM, Vision, MinIO, DB Credential을 분리한다.
- PoC 이후 Secret Manager 또는 암호화된 CI Secret을 사용한다.

## 5. 파일 보안

- 파일 크기와 MIME 검증
- 허용 확장자 제한
- 해시 저장
- 파일명 직접 경로 사용 금지
- 필요 시 악성 파일 검사
- RabbitMQ 메시지에 이미지 Binary 또는 Base64를 넣지 않는다.

## 6. 장애 대응

| 실패 | 대응 |
|---|---|
| LLM / Vision Timeout | 제한된 Retry + Exponential Backoff |
| 반복 실패 | DLQ 또는 실패 Queue 격리 |
| 단일 모델 실패 | Partial Failure 저장, 자동 승인 금지 |
| Core 재시작 | DB 상태 기반 복구 |
| Object Storage 실패 | 작업 재시도, Case 원본 상태 유지 |
| RabbitMQ 장애 | 작업 등록 상태와 Outbox 재발행 경로 유지 |

## 7. Health Check

- `/health/live`: 프로세스 생존
- `/health/ready`: DB·Queue 등 요청 처리 준비
- LLM `/health`
- Vision `/health`
- 모델 Warm-up 상태
- RabbitMQ Queue Depth
- MinIO 접근 가능성

## 8. 관측성

### System Metric

- API p50 / p95 / p99 Latency
- Error Rate
- Queue Depth
- Task Wait Time
- LLM TTFT / Total Latency
- Vision Inference Latency
- GPU Utilization / VRAM
- Retry / DLQ Count

### AI Metric

- LLM Schema Validation Failure
- Vision Low-confidence Rate
- Image Quality Failure Rate
- Alignment Score 분포
- 모델 버전별 오류율

### Business Metric

- Case 검토시간
- Approval Candidate Override율
- 위험 라우팅 오류율
- 추가 자료 요청률
- 재검토율
- 상품·결함별 반복 문제

로그와 Trace에는 `correlation_id`, `case_id`, `analysis_run_id`, `task_id`를 연결한다.

## 9. 백업

- PostgreSQL 정기 Dump 또는 Volume Snapshot
- MinIO 객체 백업
- Prompt·Policy·Threshold Export
- 복원 절차를 문서화하고 실제 복구 테스트 수행
- 개발 장비 단일 장애를 전제로 PoC 중요 데이터의 외부 백업 유지

## 10. PoC와 상용화 경계

현재 장비 구성은 개발·멘토링·제한된 PoC를 위한 것이다.

상용화 시 우선 이전 대상:

- FastAPI
- Celery Worker
- PostgreSQL
- RabbitMQ
- MinIO

LLM·Vision API 계약은 유지하고 배포 위치만 변경한다.
