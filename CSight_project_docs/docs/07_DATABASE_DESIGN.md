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
```

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
| attributes | Domain별 부가정보 JSONB |
| created_at / updated_at | 시각 |

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

- `cases(tenant_id, status, created_at)`
- `cases(tenant_id, product_ref)`
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
- Repository 수준에서 누락 방지
- PoC 이후 PostgreSQL RLS 검토
- Tenant별 정책·Prompt·Threshold 분리

## 8. Migration

- 모든 Schema 변경은 Alembic으로 관리한다.
- 수동 운영 DB 변경을 금지한다.
- Migration에는 데이터 Backfill과 Downgrade 영향을 기록한다.
- 모델 Contract 변경과 DB Migration을 동시에 배포할 경우 호환 기간을 둔다.

## 9. 보관과 삭제

별도로 확정할 항목:

- 고객 원문 보관기간
- 원본 이미지 보관기간
- 파생 이미지 및 Bounding Box 보관기간
- Audit 보관기간
- 삭제 요청 시 원본·파생·검색 Index 삭제 범위

PoC에서는 테스트 데이터와 제한된 접근권한을 기본으로 한다.
