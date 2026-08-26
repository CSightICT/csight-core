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
- 별도 Presign Hostname을 사용할 경우, 신뢰할 수 있는 HTTPS Proxy/Gateway가 서명된
  Object GET에 필요한 제한된 경로와 Method만 전달

### 사설망 전용

- PostgreSQL
- RabbitMQ
- MinIO 내부 Object API, Console, Admin API
- vLLM API
- Vision API 또는 Triton

### 차단

- 외부 → DB
- 외부 → LLM / Vision API
- LLM / Vision → 업무 DB

## 2. 인증과 권한

### MVP

- 로컬·PoC 전용 HS256 JWT Access Token
- Tenant Slug + 이메일 + Argon2id Password 로그인
- 필수 `sub`, `tenant_id`, `roles`, `iss`, `aud`, `iat`, `exp`, `jti` Claim 검증
- Token 검증 후 현재 사용자 활성 상태와 역할을 DB에서 다시 조회
- 역할: `ADMIN`, `REVIEWER`, `QUALITY_VIEWER`
- `ADMIN`·`REVIEWER`: Case 생성·조회, Evidence 업로드
- `QUALITY_VIEWER`: Case·Evidence 조회만 가능
- `ADMIN`·`REVIEWER`: Analysis Run 등록과 조회
- `QUALITY_VIEWER`: Analysis Run 조회만 가능, 등록 금지
- Tenant Scope는 요청 Body가 아닌 인증 Principal에서 결정
- 다른 Tenant의 Case/Evidence는 `404`로 숨김; `ADMIN`도 Cross-tenant 접근 불가
- Seed는 `local`/`test`에서 설정으로 명시적으로 허용한 경우에만 실행

### 기업 PoC 이후

- OIDC / SSO
- Refresh Token, Revocation, 다중 Tenant 전환
- 세부 Resource 권한
- 관리자 작업 2차 확인
- PostgreSQL RLS 검토

## 3. 개인정보와 민감정보

- 고객 문의와 이미지에는 이름, 연락처, 주소, 주문정보가 포함될 수 있다.
- 로그에 고객 원문 전체를 남기지 않는다.
- SQL 문장 로그를 명시적으로 켜더라도 Bind Parameter 값은 항상 숨긴다.
- Object Storage 접근은 짧은 만료시간의 Signed URL을 사용한다.
- Signed URL은 별도 요청에서만 발급하고 DB·로그·목록 응답에 저장하지 않는다.
- 개발 데이터는 마스킹 또는 합성 데이터를 우선한다.
- 원본과 파생 데이터의 보관기간을 분리한다.
- 삭제 요청 시 Vector Index와 보고서 파생본까지 범위를 정의한다.
- Sprint 2 LLM에는 Allowlist한 고객 메시지·주문·상품 참조·요청만 전달한다. Case Attributes,
  내부 ID, Evidence, JWT, Signed URL과 Secret은 Prompt 입력에서 제외한다.
- LLM 전체 Prompt, Raw Provider Response와 Chain-of-thought를 DB·Outbox·Broker·로그에 남기지
  않는다. 검증된 구조화 결과, Version Snapshot, Token 수와 Latency만 보존한다.

## 4. Secret 관리

- `.env`를 저장소에 Commit하지 않는다.
- `.env.example`에는 키 이름만 제공한다.
- JWT Secret은 최소 32바이트이며 Local 예시값을 운영에 재사용하지 않는다.
- 개발 Seed 비밀번호는 각 12자 이상으로 환경변수에서만 받고 로그에 남기지 않는다.
- vLLM, Vision, MinIO, DB Credential을 분리한다.
- 선택적 vLLM API Key는 Secret 타입 설정에서만 읽고 Header 값이나 Base URL Credential을
  로그에 남기지 않는다. TLS 검증은 기본 활성화한다.
- PoC 이후 Secret Manager 또는 암호화된 CI Secret을 사용한다.

## 5. 파일 보안

- 파일 비어 있음과 `MAX_UPLOAD_BYTES` 검증
- Evidence multipart 요청 전체를 `MAX_UPLOAD_BYTES + 1 MiB`로 ASGI 경계에서 제한하고,
  `Content-Length`가 없는 요청도 제한
- `ALLOWED_IMAGE_MIME_TYPES`, `ALLOWED_IMAGE_EXTENSIONS` 제한
- 실제 이미지 Decode와 Client MIME·확장자·실제 형식 일치 검증
- 폭·높이와 `MAX_IMAGE_PIXELS` 검증
- Pillow 하드 안전 한계에 맞춰 `MAX_IMAGE_PIXELS` 설정을 최대 178,956,970으로 제한
- SHA-256 저장
- 파일명 직접 경로 사용 금지
- 원본 파일명은 표시용으로만 정규화하고 Object Key는 서버 UUID로 생성
- JPEG, PNG, WebP만 허용하고 SVG는 거부
- 필요 시 악성 파일 검사
- RabbitMQ 메시지에 이미지 Binary 또는 Base64를 넣지 않는다.
- Analysis RabbitMQ Payload는 `event_id`, `tenant_id`, `case_id`, `analysis_run_id`,
  `stage_run_id`, `correlation_id` 여섯 비어 있지 않은 문자열만 허용한다.

Sprint 1~2는 EXIF 제거, 이미지 재인코딩, 개인정보 마스킹, 파생본 생성, Virus Scan을
수행하지 않는다. 원본 EXIF와 이미지 보관·삭제 정책은 실제 데이터 반입 전에 확정한다.
Production HTTPS Proxy/Gateway에도 요청 본문 크기와 동시 업로드 수 제한을 적용한다.
애플리케이션 상한은 우회 방지의 최종 경계이며, Edge 제한을 대신하지 않는다.

### Private Object와 Signed URL

- Bucket은 항상 Private다.
- `MINIO_ENDPOINT`는 Core 내부 업로드·삭제용이다.
- `MINIO_PRESIGNED_ENDPOINT`는 Client가 URL로 접근할 Hostname이다.
- `SIGNED_URL_TTL_SECONDS`는 1초~7일 범위 설정이며 Local 기본값은 900초다.
- Signed URL을 만들기 전에 내부 Endpoint의 Object HEAD로 실제 존재를 확인한다.
- Production Presign Hostname은 제한된 Object GET 경로만 Proxy하고 MinIO Console,
  Admin API, Bucket 목록과 Credential은 노출하지 않는다.

## 6. 장애 대응

| 실패 | 대응 |
|---|---|
| LLM Timeout/Unavailable | Run/Stage/Attempt `RETRY_WAITING`, 지수 Backoff와 미래 Outbox Event |
| LLM 영구 오류/최대 시도 소진 | Append-only 실패 이력과 Run/Stage `FAILED` |
| 만료된 Worker Lease | 이전 Attempt `ABANDONED`, 새 Claim Token으로 재실행 |
| 활성 Lease 중 중복 Delivery | Lease 만료 시각의 Reference-only Recovery Outbox Event 하나 저장 |
| 늦은 Worker 응답 | Claim Token 불일치로 Result·상태 쓰기 거부 |
| Vision Timeout/부분 실패 | Sprint 3 이후 범위; 자동 승인 금지 원칙 유지 |
| Core 재시작 | DB 상태 기반 복구 |
| Object Storage 실패 | 성공 응답 금지, Object 삭제와 Evidence `FAILED` 전환을 최선 노력으로 수행 |
| `AVAILABLE` DB 갱신 실패 | Object 삭제 후 `FAILED` 전환 시도, 불일치 상태 관측·복구 필요 |
| DB는 `AVAILABLE`, Object 누락 | Signed URL 성공 응답 금지, 불일치 오류 반환 후 Reconciliation 필요 |
| RabbitMQ 장애 | PENDING Outbox Backoff 재발행; 소진 시 미실행 Run/Stage `OUTBOX_DISPATCH_FAILED` |

Sprint 2는 RabbitMQ DLQ와 운영자용 수동 재처리 API를 구현하지 않는다. Dispatcher의
At-least-once Publish와 Worker Idempotency가 복구 기준이다. Celery Retry/Ack는 업무 상태의
Source of Truth가 아니며 DB 상태와 Outbox Event를 기준으로 운영한다.

## 7. Health Check

- `/health/live`: 프로세스 생존
- `/health/ready`: DB·Queue 등 요청 처리 준비
- LLM `/health`
- Vision `/health`
- 모델 Warm-up 상태
- RabbitMQ Queue Depth
- MinIO 접근 가능성
- Outbox Dispatcher Process/반복 실행 상태와 PENDING/PROCESSING Claim Age
- Stage Lease 만료와 Retry Schedule

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

Sprint 2 운영 대상은 LLM Schema/Provider 실패와 Retry 지표다. Vision, 이미지 품질과 Alignment
지표는 해당 Stage가 추가되는 후속 Sprint부터 수집한다.

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

로그와 Trace에는 상황에 따라 `correlation_id`, `tenant_id`, `user_id`, `case_id`,
`evidence_id`, `analysis_run_id`, `stage_run_id`, `event_id`, `task_id`, `operation`, `result`를
연결한다. 고객 문의 원문, Prompt/Raw LLM Response, Provider Request Body, Password, 전체 JWT,
LLM/MinIO Secret, Signed URL, 이미지 Binary, 전체 DB Connection String은 기록하지 않는다.

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

Sprint 2 Local Runtime은 API, 별도 Outbox Dispatcher, Celery Worker, RabbitMQ와 PostgreSQL을
사용한다. 기본 Provider는 Network-free Mock으로 둘 수 있고 `LLM_PROVIDER=vllm`일 때만
설정된 사설 vLLM Endpoint를 호출한다. Vision/Alignment/Policy/Routing/Review/Report/RAG
Runtime은 아직 배포 대상이 아니다.

Local Compose의 Published Port는 모두 `127.0.0.1`에만 Bind한다. 이것은 개발 편의 설정일
뿐 Production 접근 통제를 대신하지 않으며, Production에서는 HTTPS, Secret Store,
Network ACL과 제한된 Presign Gateway를 별도로 구성한다.
