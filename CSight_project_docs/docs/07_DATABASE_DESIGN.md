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
Migration `20260826_0003`은 다음 여섯 Sprint 2 분석 테이블을 추가한다.

### 분석

```text
analysis_runs
analysis_stage_runs
analysis_stage_attempts
llm_extraction_results
analysis_request_idempotency_records
outbox_events
```

Vision Result, Finding, Alignment Result는 Sprint 2 Schema에 없다.

### 정책·결정

아래는 Sprint 4 이후 미구현 범위다.

```text
policies
policy_versions
policy_rules
policy_documents
policy_chunks
routing_decisions
```

### 검토·보고서·감사

아래는 Sprint 4~5 이후 미구현 범위다. `outbox_events`만 Sprint 2 분석 테이블로 이미
구현되었으므로 이 목록에 중복하지 않는다.

```text
human_reviews
reports
audit_events
```

### 모델·프롬프트

아래 Registry Table은 미구현이다. Sprint 2 Prompt는 Code Registry로 관리하고 실행 Snapshot은
Stage/Attempt에 저장한다.

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
| id / tenant_id / case_id | Run, Tenant와 대상 Case UUID |
| pipeline_name / pipeline_version | `product_defect_text_extraction` / `1.0.0` |
| trigger_type | `USER_REQUEST` |
| status | `QUEUED`, `RUNNING`, `RETRY_WAITING`, `SUCCEEDED`, `FAILED` |
| requested_by / correlation_id | 요청 사용자와 추적 ID |
| idempotency_key / request_hash | 등록 Key와 Canonical SHA-256 |
| requested_at / started_at / completed_at | 실행 수명주기 UTC 시각 |
| failure_code / failure_message / failure_retryable | 정규화된 실패 정보 |

Run은 Pipeline 등록과 상태를 보유한다. Model/Prompt/Schema Snapshot은 실제 Provider 실행 단위인
Stage와 Attempt에 둔다. `SUCCEEDED`, `FAILED`는 Terminal이며 재분석은 새 Run Row다.

### `analysis_stage_runs`

| 컬럼군 | 설명 |
|---|---|
| id / tenant_id / analysis_run_id / stage_type | Sprint 2는 Run당 `TEXT_EXTRACTION` 하나 |
| status / attempt_count | Run과 같은 다섯 상태, 누적 시도 수 |
| provider/model name/version/revision | 등록 시점 실행 대상 Snapshot |
| prompt name/version/content hash | Code Prompt Manifest Snapshot |
| input/output schema version | Sprint 2는 `1.0` |
| execution provider/model, token counts, latency | 성공 실행 Metadata |
| claim_token / lease_expires_at | `RUNNING`일 때만 존재하는 Fencing Lease |
| next_attempt_at | `RETRY_WAITING`일 때만 존재 |
| last attempt/start/complete/failure fields | 진행·결과 감사 정보 |

조건부 Update는 Claim Token이 일치할 때만 `RUNNING` Stage를 완료한다. Outbox 발행 자체가
소진된 경우에는 아직 실행되지 않은 `QUEUED`/`RETRY_WAITING` Stage만
`OUTBOX_DISPATCH_FAILED`로 전환할 수 있다. 활성 Lease 중 중복 Delivery가 Claim에 실패하면
그 중복 처리는 `lease_expires_at`을 `available_at`으로 하는 Reference-only Recovery Outbox
Event 하나를 저장한다. 이전 Token의 늦은 쓰기는 조건부 Update에서 거부된다.

### `analysis_stage_attempts`

각 Provider 호출을 `(tenant_id, stage_run_id, attempt_number)`로 유일하게 기록한다.
`execution_token`도 유일하며 상태는 `RUNNING`, `RETRY_WAITING`, `SUCCEEDED`, `FAILED`,
`ABANDONED`다. Provider/Model/Prompt/Schema Snapshot, Token/Latency, 시작·완료 시각과 실패를
Attempt별로 보존한다. 만료 Lease 회수 시 이전 미완료 Attempt는 `ABANDONED`로 남는다.

### `llm_extraction_results`

| 컬럼군 | 설명 |
|---|---|
| id / tenant_id / analysis_run_id / stage_run_id | 성공 결과 식별·복합 Tenant FK |
| schema_version / language | 구조화 계약 식별자 |
| issue_types / claims | 검증된 JSONB 배열 |
| requested_action / missing_information / summary | 의사결정 없는 정규화 결과 |

Run당·Stage당 최대 하나를 Unique Constraint로 강제한다. Repository는 Add/Get만 제공하고
Update/Delete 경로가 없다. 전체 Prompt, Raw Provider Response와 Chain-of-thought Column은
존재하지 않는다.

### `analysis_request_idempotency_records`

`operation = analysis.create.v1`이며 `(tenant_id, operation, idempotency_key)`가 Unique다.
Case ID, Canonical Request Hash, 생성된 Run ID, 최초 응답 `202`, 생성·만료 시각을 보존한다.
Run FK는 같은 Transaction에서 Idempotency Claim을 먼저 확보할 수 있도록 Deferred다. 같은
Key/Hash는 기존 Run을 재생하고 다른 Hash는 충돌이다.

### `outbox_events`

상태는 `PENDING`, `PROCESSING`, `PUBLISHED`, `FAILED`다. Aggregate는 `analysis_run`, Event는
`analysis.requested.v1` `1.0`만 허용한다. DB Payload에는 Event ID/Type/Version, Tenant/Case/
Run/Stage/Correlation ID와 발생 시각을 저장한다. Dispatcher는 이 Payload를 검증한 뒤 Queue에
`event_id`, `tenant_id`, `case_id`, `analysis_run_id`, `stage_run_id`, `correlation_id` 여섯
식별자만 전달한다.

Claim 시각·Token·Dispatcher ID, Attempt Count, 다음 발행 시각, 발행 시각과 제한된 실패
문구를 보존한다. `FOR UPDATE SKIP LOCKED` Claim 후 Commit하고 Broker 발행 뒤 같은 Token으로
완료한다. Customer 원문, Prompt, Raw Response, JWT, Signed URL과 Secret은 Payload에 없다.
Provider Retry와 활성 Lease Recovery도 미래 `PENDING` Outbox Row로 내구화하며 Celery Retry
상태를 업무 Source of Truth로 사용하지 않는다.

### `human_reviews`

이 Table은 Sprint 4 이후 설계 예시이며 Migration `20260826_0003`에는 없다.

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
- Strict Schema로 검증된 LLM Issue/Claim/Missing Information 배열
- 식별자만 포함하고 허용 Key를 DB Constraint로 제한한 Outbox Event Envelope

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
- `analysis_runs(tenant_id, case_id, requested_at, id)`
- `analysis_stage_runs(tenant_id, analysis_run_id, created_at, id)`
- `analysis_stage_runs`의 `RUNNING lease_expires_at`, `RETRY_WAITING next_attempt_at` 부분 Index
- `analysis_stage_attempts(tenant_id, stage_run_id, attempt_number)`
- `llm_extraction_results(tenant_id, analysis_run_id)`
- `analysis_request_idempotency_records(expires_at)`
- `outbox_events`의 `PENDING available_at`, `PROCESSING claimed_at` 부분 Index
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
- 모든 Tenant-scoped 업무 Repository 메서드가 `tenant_id`를 명시적으로 요구. 단,
  Dispatcher의 Cross-tenant `claim_batch`/Stale Recovery는 반환 Row의 Tenant를 사용하고 이후
  Mark/Release/Fail은 Tenant Scope를 요구
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

Sprint 2의 `20260826_0003`은 `0002` 위에 정확히 여섯 Analysis/Outbox Table, Tenant 복합 FK,
상태·Claim·Payload Check Constraint와 Index를 추가한다. Vision, Alignment, Policy, Routing,
Review, Report, RAG Table은 이 Migration에 없다. 설계 근거는
[ADR-0009](adr/0009-transactional-outbox-and-fenced-analysis-execution.md),
[ADR-0010](adr/0010-code-prompt-registry-and-structured-output-retention.md),
[ADR-0011](adr/0011-separate-case-and-analysis-lifecycles.md)이다.

## 9. 보관과 삭제

별도로 확정할 항목:

- 고객 원문 보관기간
- 원본 이미지 보관기간
- 파생 이미지 및 Bounding Box 보관기간
- Audit 보관기간
- 삭제 요청 시 원본·파생·검색 Index 삭제 범위
- 실패·중단된 Evidence Row와 고아 Object의 Reconciliation 주기
- Idempotency Row의 Cleanup과 Key 재사용 정책
- 완료·실패 Outbox Event와 Analysis Attempt 이력의 보관기간·Cleanup 정책

PoC에서는 테스트 데이터와 제한된 접근권한을 기본으로 한다.

Case와 Evidence의 Hard Delete API는 Sprint 1에 없다. 보관·삭제 요구가 확정되기 전까지
Migration이나 운영 명령으로 임의 삭제하지 않는다.

## 10. Sprint 3 Vision Persistence

`20260826_0004`는 기존 revision을 수정하지 않고 아래를 추가한다.

| 테이블 | 목적 |
|---|---|
| `analysis_run_evidence` | Run 시작 시 evidence ID, 안정 position, SHA-256 Snapshot |
| `vision_analysis_results` | evidence별 canonical quality/result와 provider/model/version metadata |
| `vision_detections` | result별 순번, native provenance, canonical label, confidence, normalized bbox |

모든 FK는 tenant를 포함하고 `ON DELETE RESTRICT`다. `(tenant, run, evidence)` Vision Result와
Snapshot evidence/position은 unique다. Confidence와 coordinate 범위/순서는 DB check constraint로
재검증한다. Result/Detection/Snapshot update/delete repository는 제공하지 않는다.

Run pipeline constraint에 multimodal `1.0.0`을, status에 `PARTIAL_SUCCESS`를 추가한다.
Downgrade는 Detection→Result→Snapshot 역순으로 새 테이블만 제거한 뒤 Sprint 2 constraint를
복원한다.

## 11. Sprint 4A LLM v2 Persistence

`20260826_0005`는 기존 `llm_extraction_results`를 변경하지 않고
`llm_extraction_results_v2`를 추가한다. v2 row는 복수 requested actions, text ambiguities,
system missing, action consistency와 completeness rule version을 보존하며 Run/Stage당 하나다.
Repository는 add/get만 제공한다. Policy Corpus는 아직 DB table로 적재하지 않는다.

## 12. Sprint 4B Policy Retrieval Persistence

`20260826_0006`은 ingestion run, immutable document, clause, embedding profile, clause embedding,
index version 6개 table을 추가한다. Vector dimension은 migration type에 추측해 하드코딩하지 않고
profile/row의 실제 dimension 1024로 검증한다. Tenant/effective/status index와 array GIN index,
성공 ingestion identity 및 tenant/index당 one-active partial unique index를 둔다.
