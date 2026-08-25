# 07. Database Design

## 1. 설계 원칙

- 업무 DB의 단일 소유자는 Core Backend다.
- 모델 서버는 DB에 직접 접근하지 않는다.
- 분석 결과는 Append-only로 저장한다.
- 공통 필드는 정규 컬럼, Domain별 유동 필드는 제한적으로 JSONB를 사용한다.
- 모든 업무 테이블은 Tenant 경계를 고려한다.
- 버전과 유효기간을 명시한다.

## 2. Core 테이블

### 조직·사용자

```text
tenants
users
roles
user_roles
```

### Case·Evidence

```text
cases
case_evidence
case_status_history
idempotency_records
```

위 8개 조직·사용자·Case·Evidence 테이블은 Migration `20260826_0002`에서 생성한다.
아래 분석 이후 테이블은 설계 목표이며 Sprint 1 Schema에는 아직 없다.

### 분석

```text
analysis_runs
llm_analysis_results
vision_analysis_results
analysis_findings
alignment_results
```

### 정책·결정

```text
policies
policy_versions
policy_rules
policy_documents
policy_chunks
routing_decisions
```

### 검토·보고서·감사

```text
human_reviews
reports
audit_events
outbox_events
```

### 모델·프롬프트

```text
model_registry
prompt_templates
prompt_versions
threshold_versions
retrieval_index_versions
```

## 3. 핵심 컬럼 예시

### `cases`

| 컬럼 | 설명 |
|---|---|
| id | Case ID |
| tenant_id | 고객사 |
| domain_type | product_defect_cs 등 |
| status | 현재 상태 |
| order_ref | 주문 참조 |
| product_ref | 상품 참조 |
| customer_message | 고객 문의 원문 |
| requested_action | 정의된 고객 요청 Enum |
| attributes | Domain별 부가정보 JSONB |
| created_by | 같은 Tenant의 생성 사용자 |
| created_at / updated_at | 시각 |

`id`, `tenant_id`, `created_by`는 UUID다. Case는 `product_defect_cs`, `RECEIVED`로
시작하며 고객 원문과 주문·상품 참조는 빈 문자열일 수 없다.

### `case_evidence`

| 컬럼 | 설명 |
|---|---|
| id / tenant_id / case_id | Evidence, Tenant, Case UUID |
| evidence_type | 공개 업로드는 `IMAGE` |
| upload_status | `PENDING`, `AVAILABLE`, `FAILED` |
| storage_bucket / object_key | Private Object 위치 |
| original_filename | 경로를 제거하고 정규화한 표시용 파일명 |
| content_type / size_bytes / sha256 | 실제 Decode 기반 MIME, 크기, SHA-256 |
| width / height | 이미지 폭·높이 |
| created_by | 같은 Tenant의 업로드 사용자 |
| created_at / updated_at | UTC 시각 |

이미지 Binary와 Signed URL은 이 테이블에 저장하지 않는다. `(storage_bucket,
object_key)`는 고유하며 이미지 Evidence의 크기·해시·폭·높이는 DB Check Constraint로도
검증한다.

### `case_status_history`

| 컬럼 | 설명 |
|---|---|
| id / tenant_id / case_id | 이력, Tenant, Case UUID |
| from_status / to_status | 이전·다음 Case 상태; 최초 `from_status`는 `NULL` |
| actor_id / reason | 같은 Tenant의 Actor와 전환 사유 |
| occurred_at | UTC 전환 시각 |

최초 이력은 Case와 같은 Transaction에 저장하고 `reason = case_created`를 사용한다.

### `idempotency_records`

| 컬럼 | 설명 |
|---|---|
| id / tenant_id | 레코드와 Tenant UUID |
| operation | Sprint 1은 `case.create.v1` |
| idempotency_key | Client Header 값, 최대 255자 |
| request_hash | 정규화한 요청의 SHA-256 |
| resource_type / resource_id | `case`와 같은 Tenant의 Case UUID |
| response_status | 최초 성공 HTTP Status (`201`) |
| created_at / expires_at | 생성 시각과 24시간 Retention 메타데이터 |

`(tenant_id, operation, idempotency_key)` Unique Constraint와 PostgreSQL Conflict 처리가
동시 요청의 중복 생성을 방지한다. Sprint 1에는 만료 Row Cleanup과 만료 후 Key 재사용이
없다.

### `analysis_runs`

| 컬럼 | 설명 |
|---|---|
| id | Analysis Run ID |
| case_id | 대상 Case |
| status | 실행 상태 |
| llm_model_version | LLM 버전 |
| vision_model_version | Vision 버전 |
| prompt_version | Prompt 버전 |
| policy_version | 적용 정책 버전 |
| threshold_version | Threshold 버전 |
| started_at / completed_at | 실행 시각 |
| error_code / error_detail | 실패 정보 |

### `human_reviews`

| 컬럼 | 설명 |
|---|---|
| id | Review ID |
| case_id | 대상 Case |
| analysis_run_id | 검토한 분석 |
| recommended_action | AI 권고 |
| final_action | 담당자 결정 |
| override_reason_code | 수정 이유 코드 |
| note | 메모 |
| reviewer_id | 담당자 |
| reviewed_at | 확정 시각 |

## 4. JSONB 사용 기준

JSONB가 적합한 경우:

- Domain별 선택적 속성
- 원본 모델 응답 보존
- 빠르게 변경되는 부가 메타데이터

정규 컬럼이 필요한 경우:

- 검색·정렬·통계에 자주 사용
- 외래키 또는 제약조건 필요
- 정책·금액·기간처럼 정합성이 중요
- 보안·감사 필터에 사용

완전한 EAV 모델은 사용하지 않는다.

## 5. 인덱스

초기 권장:

- `cases(tenant_id, created_at, id)`
- `cases(tenant_id, status, created_at, id)`
- `cases(tenant_id, product_ref)`
- `cases(tenant_id, order_ref)`
- `case_evidence(tenant_id, case_id, created_at, id)`
- `case_evidence(case_id, sha256)`
- `case_status_history(tenant_id, case_id, occurred_at, id)`
- `idempotency_records(expires_at)`
- `analysis_runs(case_id, created_at desc)`
- `human_reviews(case_id, reviewed_at desc)`
- `policy_versions(tenant_id, effective_from, effective_to)`
- `audit_events(tenant_id, case_id, occurred_at)`
- `policy_chunks`의 Vector Index는 데이터 규모를 측정한 뒤 HNSW 또는 IVF를 선택

## 6. 권한 분리

- `api_user`: 업무 CRUD
- `worker_user`: 분석·결과·작업 상태 쓰기, 사용자 관리 제한
- `read_analytics_user`: 비식별 집계 조회
- 모델 서버용 DB 계정은 생성하지 않는다.

## 7. Multi-tenancy

MVP는 Shared Database + `tenant_id` 방식으로 시작한다.

- 모든 조회에 Tenant Scope 적용
- 모든 업무 Repository 메서드가 `tenant_id`를 명시적으로 요구
- Case, Evidence, 상태 이력, 사용자 관계에 복합 Tenant Foreign Key 적용
- 다른 Tenant ID 조회는 존재 여부를 감추는 Not Found로 변환
- Repository와 API Test에서 필터 누락 방지
- PoC 이후 PostgreSQL RLS 검토
- Tenant별 정책·Prompt·Threshold 분리

## 8. Migration

- 모든 Schema 변경은 Alembic으로 관리한다.
- 수동 운영 DB 변경을 금지한다.
- Migration에는 데이터 Backfill과 Downgrade 영향을 기록한다.
- 모델 Contract 변경과 DB Migration을 동시에 배포할 경우 호환 기간을 둔다.

Sprint 1의 `20260826_0002`는 Baseline `20260825_0001`을 수정하지 않고 그 위에 Tenant,
Identity, Case, Evidence, 상태 이력, Idempotency Schema를 추가한다. Downgrade는 FK 의존성의
역순으로 이 8개 테이블과 인덱스를 제거하므로 해당 Sprint 1 데이터가 모두 삭제된다.

## 9. 보관과 삭제

별도로 확정할 항목:

- 고객 원문 보관기간
- 원본 이미지 보관기간
- 파생 이미지 및 Bounding Box 보관기간
- Audit 보관기간
- 삭제 요청 시 원본·파생·검색 Index 삭제 범위
- 실패·중단된 Evidence Row와 고아 Object의 Reconciliation 주기
- Idempotency Row의 Cleanup과 Key 재사용 정책

PoC에서는 테스트 데이터와 제한된 접근권한을 기본으로 한다.

Case와 Evidence의 Hard Delete API는 Sprint 1에 없다. 보관·삭제 요구가 확정되기 전까지
Migration이나 운영 명령으로 임의 삭제하지 않는다.
