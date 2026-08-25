# Sprint 1 Case & Evidence 작업 기록

- 작업일: 2026-08-26 (Asia/Seoul)
- 범위: 인증된 Tenant 사용자의 Case 생성·조회와 이미지 Evidence 저장 Vertical Slice
- 작업 Branch: `feature/sprint-1-case-evidence`
- Git Commit/Push: Closeout 검증 후 이 기록을 포함한 로컬 기준점 Commit만 생성, Push 미수행

## 1. Sprint 목표

개발 Identity Seed부터 JWT 로그인, Tenant Scope Case 생성·목록·상세·상태 이력, 이미지
검증, Private MinIO 저장, Evidence 메타데이터와 Signed URL까지 하나의 실행 가능한 흐름으로
연결한다. Case/Evidence 접수는 실제 LLM·Vision 분석을 시작하지 않는다.

## 2. 작업 전 Foundation 상태

Sprint 1 변경 전 다음 Sprint 0 회귀 검사를 실제로 다시 실행했다.

| 검사 | 상태 | 실제 결과 |
|---|---|---|
| `uv sync --frozen --group dev` | PASS | 기존 Lockfile 기준 61 Package 확인 |
| Ruff | PASS | 변경 전 Lint 통과 |
| Ruff Format Check | PASS | 변경 전 80 files 확인 |
| Pyright strict | PASS | 변경 전 0 errors |
| CI-safe pytest | PASS | 37 passed, 4 deselected |
| Architecture Boundary | PASS | 2 passed |
| Compose Build/Start | PASS | API, Worker, PostgreSQL, RabbitMQ, MinIO 5개 장기 서비스 Healthy |
| Baseline Migration | PASS | `20260825_0001` 적용 |
| Health | PASS | `/health/live`, `/health/ready` 모두 HTTP 200 |

## 3. 구현 범위

### 인증과 Tenant

- `tenant_slug`, 이메일, 비밀번호를 받는 로컬·PoC 로그인
- Argon2id Password Hash와 HS256 JWT Access Token
- Issuer, Audience, 만료, 필수 Claim 검증
- Token 검증 후 DB에서 현재 사용자 활성 상태와 역할 재조회
- Principal에서만 `tenant_id`를 가져오며 요청 Body·Query·Form의 Tenant를 신뢰하지 않음
- 모든 Case·History·Evidence·Idempotency Repository 메서드가 명시적 `tenant_id`를 받고,
  쓰기 엔티티의 Tenant 불일치를 SQL 실행 전에 거부
- `ADMIN`, `REVIEWER`: Case 생성·조회, Evidence 업로드
- `QUALITY_VIEWER`: Case·Evidence 조회만 가능
- 다른 Tenant의 Case/Evidence는 존재 여부를 숨기는 `404`
- `local`/`test`에서만 명시적으로 허용되는 반복 실행 안전 Seed

Seed Identity:

| 구분 | 값 |
|---|---|
| Tenant | `csight-demo` |
| Admin | `admin@csight.demo` |
| Reviewer | `reviewer@csight.demo` |
| Quality Viewer | `viewer@csight.demo` |

비밀번호는 환경변수로만 받고 문서·Migration·로그에 기록하지 않는다.

### Case

- `CreateCase`, `ListCases`, `GetCase`, `GetCaseStatusHistory` Use Case
- `product_defect_cs` Domain과 정의된 Requested Action/Case Status Enum
- 공백 고객 문의 및 JSON 비호환 `attributes` 거부
- UUIDv4, UTC 시각, 초기 `RECEIVED` 상태
- 생성 Transaction에 `from_status = null`, `to_status = RECEIVED`,
  `reason = case_created`인 최초 이력 포함
- Status, 주문·상품 참조, 생성 기간, 페이지 필터
- `created_at DESC, id DESC` 안정 정렬과 페이지 크기 최대 100
- 목록에서 고객 문의 원문·Signed URL 제외
- Case Hard Delete와 임의 PATCH 미지원

### Case 생성 Idempotency

- 선택적 `Idempotency-Key` Header
- `(tenant_id, operation=case.create.v1, key)` DB Unique Scope
- 정규화한 요청 Body의 Canonical JSON SHA-256
- 동일 Key·Body는 기존 Case를 `200`으로 재생, 새 생성은 `201`
- 같은 Key·다른 Body는 `409 IDEMPOTENCY_KEY_REUSED`
- `expires_at`은 생성 후 24시간으로 기록하지만 Sprint 1에는 Cleanup과 만료 후 Key 재사용이
  없음

### Evidence

- JPEG, PNG, WebP `IMAGE` Multipart 업로드
- 독립 `HashingPort`와 `BoundedSha256Hasher`로 한 번의 제한된 Streaming Read에서 크기와
  SHA-256을 계산하고 Stream을 되감음
- `FileInspectorPort`와 Pillow Adapter로 허용 MIME·확장자, 실제 Decode/형식 일치,
  폭·높이와 Pixel 수 검증
- 빈 파일·초과 크기 차단과 정규화한 표시용 원본 파일명
- endpoint parsing 전 ASGI 경계에서 multipart 요청 전체를
  `MAX_UPLOAD_BYTES + 1 MiB`로 제한하고 `Content-Length` 없는 요청도 차단
- 원본 파일명과 무관한 Object Key:

  ```text
  tenants/{tenant_id}/cases/{case_id}/evidence/{evidence_id}/original
  ```

- Private MinIO 원본과 PostgreSQL 메타데이터 분리
- `PENDING` Commit → Object 저장·확인 → `AVAILABLE` Commit
- MinIO `PUT` 뒤 실제 `HEAD/stat`의 크기·MIME·SHA-256 metadata 일치 확인
- Storage 또는 최종 DB 실패 시 Object 삭제와 `FAILED` 전환을 각각 최선 노력으로 수행
- 보상 삭제·상태 전환 자체가 실패하면 ID와 단계·오류 유형만 구조화 로그로 관측
- `AVAILABLE` Evidence만 설정된 TTL의 Signed GET URL 발급
- URL 발급 직전 내부 Object HEAD를 확인하고 DB만 `AVAILABLE`인 누락 Object에는 성공 금지
- Token과 Signed URL 응답에 Cache 방지 Header 적용
- Signed URL, Credential, Binary는 DB·로그·목록 응답에 저장하지 않음
- SQL Echo를 켜도 고객 원문을 포함한 Bind Parameter 값은 항상 숨김

## 4. Migration

새 Revision:

```text
20260825_0001 (pgvector baseline)
        ↓
20260826_0002 (Sprint 1 identity, Case, Evidence, idempotency)
```

추가한 테이블:

```text
tenants
users
roles
user_roles
cases
case_evidence
case_status_history
idempotency_records
```

모든 업무 관계에 Tenant FK를 포함하고, 사용자 이메일과 Case/Evidence 연결, 역할,
상태·Enum, SHA-256, 이미지 크기, Object Key, Idempotency Scope에 Constraint를 적용했다.
Tenant·상태·생성시각·ID 안정 정렬, 주문·상품 참조, Evidence SHA, 상태 이력,
Idempotency 만료시각 인덱스를 추가했다.

Downgrade는 FK 역순으로 Sprint 1의 8개 테이블과 해당 인덱스를 제거한다. 실행하면 Sprint 1
Identity, Case, Evidence와 Idempotency 데이터가 모두 삭제되므로 운영 데이터가 있는
환경에서 자동 수행하지 않는다.

## 5. HTTP API

| Method | Path | 인증·권한 | 설명 |
|---|---|---|---|
| POST | `/api/v1/auth/token` | 공개 | 로컬·PoC JWT 로그인 |
| GET | `/api/v1/auth/me` | Bearer | 현재 Principal |
| POST | `/api/v1/cases` | Admin, Reviewer | Case 생성; 새 요청 201, 재생 200 |
| GET | `/api/v1/cases` | 모든 역할 | Tenant Scope 필터·페이지 목록 |
| GET | `/api/v1/cases/{case_id}` | 모든 역할 | Evidence·이력을 포함한 상세 |
| GET | `/api/v1/cases/{case_id}/status-history` | 모든 역할 | 상태 이력 |
| POST | `/api/v1/cases/{case_id}/evidence` | Admin, Reviewer | 이미지 업로드 |
| GET | `/api/v1/cases/{case_id}/evidence` | 모든 역할 | Evidence 목록 |
| GET | `/api/v1/cases/{case_id}/evidence/{evidence_id}` | 모든 역할 | Evidence 메타데이터 |
| POST | `/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url` | 모든 역할 | Signed URL 생성 |

OpenAPI는 FastAPI 앱의 `/docs`와 `/openapi.json`에서 확인한다. 상세 Body, 응답, 권한과 오류
매핑은
[`CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md`](../../CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md)에
기록했다.

## 6. 설정과 실행

`.env.example`을 복사한 뒤 실제 Local Secret과 12자 이상의 역할별 Seed Password를
`.env`에만 설정한다. Secret을 문서, Issue, Shell 출력 또는 Git에 추가하지 않는다.

```bash
cp .env.example .env
uv sync --frozen --group dev
make up
make migrate
make seed
```

Seed는 `DEVELOPMENT_SEED_ENABLED=true`와 `ENVIRONMENT=local` 또는 `test`를 요구하며
Production/Staging을 거부한다. 로그인, Case 생성, Evidence 업로드, 조회와 Signed URL의
복사 가능한 `curl` 흐름은 [README](../../README.md#sprint-1-api-흐름)에 있다.

Evidence 설정:

```text
MAX_UPLOAD_BYTES
ALLOWED_IMAGE_MIME_TYPES
ALLOWED_IMAGE_EXTENSIONS
MAX_IMAGE_PIXELS
SIGNED_URL_TTL_SECONDS
MINIO_ENDPOINT
MINIO_PRESIGNED_ENDPOINT
```

Local `MINIO_ENDPOINT`는 Core 내부 통신, `MINIO_PRESIGNED_ENDPOINT`는 Client 접근 URL
생성에 사용한다. Production에서는 Private Bucket을 유지하고 신뢰할 수 있는 HTTPS
Proxy/Gateway가 서명된 Object GET에 필요한 제한된 경로만 노출한다. MinIO Console과
Admin API는 Private Network에 둔다.

## 7. 최종 검증 결과

아래 결과는 2026-08-26에 Sprint 1 구현과 독립 Closeout 감사 후 실제로 실행한 값이다.

| 검사 | 상태 | 실제 결과 |
|---|---|---|
| Ruff | PASS | 전체 Lint 통과 |
| Ruff Format Check | PASS | Sprint 1 Commit 후보 범위 전체 형식 통과 |
| Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| CI-safe pytest | PASS | 189 passed, 18 deselected |
| 대상별 pytest | PASS | Unit 168, Architecture 4, Contract 14, 기존 E2E 3, HTTP API 15; 중복 포함 |
| Core Integration pytest | PASS | 18 passed, 189 deselected |
| 실제 장애 보상 Integration | PASS | MinIO partial write와 PostgreSQL `AVAILABLE` 전환 실패 2건 |
| MinIO 대상 Integration | PASS | Private Signed/Unsigned 접근과 장애 보상 묶음 3 passed |
| Live HTTP Vertical Slice | PASS | 초기 17개 검사와 최종 이미지 재빌드 후 9개 Smoke 통과 |
| Live Multipart 조기 차단 | PASS | Body 전송 전 `413 FILE_TOO_LARGE` 확인 |
| Compose | PASS | API, Worker, PostgreSQL, RabbitMQ, MinIO 5개 장기 서비스 Healthy |
| Alembic Upgrade | PASS | Head `20260826_0002` |
| Alembic Schema Drift | PASS | `alembic check`: 새 Upgrade 작업 없음 |
| 격리 Migration 수명주기 | PASS | 빈 DB→Head, Sprint 0→1, Head→Sprint 0→Head와 복합 Tenant FK 거부 |
| Development Seed | PASS | 같은 설정으로 2회 성공, 중복 Identity 없음 |
| 검증 데이터 정리 | PASS | 업무 테이블 4개 Row와 MinIO Object 모두 0 |

Closeout 감사의 발견·수정 내역과 로컬 Commit 범위는
[`SPRINT_1_CLOSEOUT.md`](SPRINT_1_CLOSEOUT.md)를 기준으로 한다. 저장소 루트의 별도 미추적
Kaputt 비전 아키텍처 문서는 Sprint 1 범위가 아니므로 수정하거나 Commit하지 않았다.

Live 17개 HTTP 검사는 명시적 Seed를 사용하는 실제 Compose 환경에서 로그인,
`/auth/me`, Case 생성과 재생, 목록·상세·상태 이력, Evidence 업로드·조회, Signed URL
발급과 Object GET 등 단일 Seed Tenant의 실행 경로를 확인한 결과다. 최종 이미지 재빌드
뒤 9개 Smoke는 Health, 로그인 Cache 방지 Header, `/auth/me`, Case
생성·재생, Evidence 업로드, 상세, Signed URL Cache 방지 Header와 Object Download를 다시
확인했다. 별도의 PostgreSQL/API Integration Suite는 Tenant A/B Fixture로 Repository
필터, Idempotency 범위와 다른 Tenant
Case·Evidence 요청의 `404` 격리를 검증했으며 위 18 passed에 포함된다. Live 검사와
Integration 격리 검사를 같은 결과로 합쳐 표현하지 않는다. 전체 JWT, Seed Password,
Signed URL과 Connection String은 검증 기록에 남기지 않았다.

## 8. 알려진 제한사항

- 실제 LLM·Vision, Analysis Run, 비동기 `202`, Policy, Routing, Review, Report, RAG를
  구현하지 않았다.
- Evidence 업로드 Idempotency가 없어 동일 파일의 재전송은 별도 Evidence를 만들 수 있다.
- PostgreSQL과 MinIO는 분산 Transaction이 아니다. 강제 종료와 보상 실패가 겹치면 고아
  Object 또는 `PENDING`/`FAILED` Row가 남을 수 있으나 Sprint 1에는 자동 Reconciliation과
  Orphan Cleanup이 없다.
- 이미지 EXIF 제거, 재인코딩, 개인정보 마스킹, 파생본, Virus Scan을 수행하지 않는다.
- 애플리케이션의 multipart 상한과 별개로 Production Edge의 요청 본문·동시 업로드 제한은
  배포 환경에서 설정하고 부하 검증해야 한다.
- 고객 원문·원본 이미지·Audit·Idempotency의 Retention과 삭제 정책이 미확정이다.
- Refresh Token, Revocation, OIDC/SSO, 다중 Tenant 전환, PostgreSQL RLS는 후속 범위다.
- Idempotency의 24시간 `expires_at`은 메타데이터이며 Cleanup과 Key 재사용을 지원하지
  않는다.
- MinIO Production Gateway와 Secret Rotation 절차는 배포 환경에서 별도 검증해야 한다.

## 9. Sprint 2 인계

Sprint 2는 현재 Case/Evidence Port와 Tenant 경계를 유지하면서 다음을 연결한다.

- Case에 새 Append-only Analysis Run 생성
- API의 `202 Accepted`와 `analysis_run_id`
- 얇은 Celery Task에서 Application 분석 Use Case 호출
- RabbitMQ 재전달 Idempotency, Retry, Timeout과 실패 이력
- vLLM Adapter와 구조화 출력 Contract
- Prompt, Model, Policy, Threshold, Embedding, Retrieval Index 버전 참조

Case/Evidence 접수와 분석 시작을 별도 API로 유지하고, 재분석은 기존 결과를 덮어쓰지 않고
새 Analysis Run을 생성해야 한다.
