# 05. API and Event Contracts

## Operator assignment and review summary (ADR-0109)

- `GET /api/v1/human-review-assignees` is administrator-only and returns active tenant users eligible for review assignment.
- `POST /api/v1/human-review-tasks/{task_id}/assign` accepts `expected_version`, `assignee_id`, and an audit rationale. It appends assignment history and returns `409` on stale task versions.
- Operator case/review projections restrict reviewer-only accounts to current assignments or their immutable completed decisions. Administrators retain tenant-wide views.
- Review task detail additively returns `inquiry_summary`, cited clause `text`, and `policy_similarity`. `NEAREST` is ordered by absolute cosine distance from the versioned `0.65` reference; `LEAST` is ordered by ascending cosine. Similarity evidence is absent for legacy runs and is advisory only.
- `WAITING_FOR_EVIDENCE` retains the current assignee and assignment interval. Resume returns the task to `CLAIMED`; it does not reopen an unassigned claim race.

## 1. 계약 원칙

- 외부 API는 `/api/v1`으로 버전 관리한다.
- Sprint 1의 Case 생성과 Evidence 업로드는 동기 요청이다. 새 리소스는 `201 Created`,
  Case Idempotency 재생은 `200 OK`를 반환한다.
- 장시간 분석 요청은 Sprint 2부터 `202 Accepted`를 반환한다.
- Case 생성은 선택적 `Idempotency-Key`, Sprint 2 Analysis 등록은 필수
  `Idempotency-Key`를 지원한다. 두 Operation은 별도 Tenant-scoped Claim을 사용한다.
  Evidence 업로드 Idempotency는 후속 범위다.
- Event에는 `event_version`, 모델 출력에는 `schema_version`을 포함한다.
- 모델 고유 출력은 외부에 직접 노출하지 않고 공통 Schema로 변환한다.
- Sprint 2는 검증된 정규화 결과만 저장하며 전체 Prompt와 Raw Provider Response를 저장하거나
  API로 노출하지 않는다.
- 모든 Case·Evidence·Analysis API는 Bearer 인증을 요구한다. `tenant_id`는 입력으로 받지 않고
  현재 Principal에서 결정한다.
- 요청 Schema는 알 수 없는 필드를 거부한다. 따라서 Body에 `tenant_id`를 넣으면
  `422 VALIDATION_ERROR`다.
- 날짜·시각은 UTC Offset을 포함한 RFC 3339 형식을 사용하고 ID는 불투명 문자열로
  취급한다.

## 2. Sprint 1 HTTP API

### 인증

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/v1/auth/token` | 불필요 | 명시적 local/test 호환 프로필에서만 Access Token 발급 |
| GET | `/api/v1/auth/me` | OIDC session 또는 local/test Bearer | 현재 사용자, Tenant와 현재 역할 조회 |

### Case

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/api/v1/cases` | Admin, Reviewer | Case와 `RECEIVED` 최초 이력 생성 |
| GET | `/api/v1/cases` | 모든 역할 | Tenant Scope 필터·페이지 목록 |
| GET | `/api/v1/cases/{case_id}` | 모든 역할 | Evidence·상태 이력을 포함한 상세 |
| GET | `/api/v1/cases/{case_id}/status-history` | 모든 역할 | 오래된 순서의 상태 이력 |

Case 목록 Query:

| 이름 | 형식 | 기본값·제약 |
|---|---|---|
| `status` | Case Status Enum | 선택 |
| `order_ref` | 문자열 | 선택, 정확히 일치 |
| `product_ref` | 문자열 | 선택, 정확히 일치 |
| `created_from` | Offset 포함 DateTime | 선택, 양 끝 포함 |
| `created_to` | Offset 포함 DateTime | 선택, 양 끝 포함 |
| `page` | 정수 | 기본 1, 최소 1 |
| `page_size` | 정수 | 기본 20, 1~100 |

정렬은 `created_at DESC, id DESC`다. 목록 항목은 전체 `customer_message`, `attributes`,
Evidence, 상태 이력, Signed URL을 포함하지 않는다.

### Evidence

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/api/v1/cases/{case_id}/evidence` | Admin, Reviewer | Multipart 이미지 업로드 |
| GET | `/api/v1/cases/{case_id}/evidence` | 모든 역할 | Evidence 메타데이터 목록 |
| GET | `/api/v1/cases/{case_id}/evidence/{evidence_id}` | 모든 역할 | Evidence 메타데이터 상세 |
| POST | `/api/v1/cases/{case_id}/evidence/{evidence_id}/access-url` | 모든 역할 | 짧게 만료되는 Signed GET URL 생성 |

업로드는 `multipart/form-data`의 필수 `file`과 `evidence_type=IMAGE`를 받는다. 응답은
Storage Credential, Bucket/Object Key, Binary 또는 Signed URL을 노출하지 않는다.

### 역할

| 역할 | Case 생성 | Case/Evidence 조회 | Evidence 업로드·접근 URL |
|---|---:|---:|---:|
| `ADMIN` | 허용 | 허용 | 허용 |
| `REVIEWER` | 허용 | 허용 | 허용 |
| `QUALITY_VIEWER` | 금지 | 허용 | 업로드 금지, 접근 URL 허용 |

Analysis 권한은 별도로 `ANALYSIS_CREATE`, `ANALYSIS_READ`로 검사한다.

| 역할 | Analysis 등록 | Analysis 목록·상세 조회 |
|---|---:|---:|
| `ADMIN` | 허용 | 허용 |
| `REVIEWER` | 허용 | 허용 |
| `QUALITY_VIEWER` | 금지 | 허용 |

인증되지 않은 요청은 `401`, 역할이 부족하면 `403`이다. 다른 Tenant의 ID는 역할과
무관하게 `404`로 숨긴다.

## 3. 인증 계약

```http
POST /api/v1/auth/token
Content-Type: application/json
```

```json
{
  "tenant_slug": "csight-demo",
  "email": "reviewer@csight.demo",
  "password": "<local-seed-password>"
}
```

```json
{
  "access_token": "<redacted-jwt>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

`expires_in`은 설정된 Access Token 수명을 초 단위로 반환한다. 현재 사용자는 별도
`GET /api/v1/auth/me`에서 확인한다. Token 응답에는 `Cache-Control: no-store`와
`Pragma: no-cache`를 적용한다.

```json
{
  "user_id": "<uuid>",
  "tenant_id": "<uuid>",
  "email": "reviewer@csight.demo",
  "display_name": "Demo Reviewer",
  "roles": ["REVIEWER"]
}
```

## 4. Case 계약

### Case 생성

```http
POST /api/v1/cases
Authorization: Bearer <access-token>
Idempotency-Key: <optional-tenant-scoped-key>
Content-Type: application/json
```

```json
{
  "order_ref": "ORD-2026-0001",
  "product_ref": "SKU-001",
  "customer_message": "용기 하단이 찌그러졌고 내용물이 샜습니다. 교환을 요청합니다.",
  "requested_action": "EXCHANGE",
  "attributes": {
    "order_amount": 42000,
    "days_since_purchase": 3
  }
}
```

응답:

```json
{
  "case_id": "<uuid>",
  "status": "RECEIVED",
  "created_at": "2026-08-26T13:00:00Z"
}
```

새 Key 또는 Key 없는 새 생성은 `201`이다. 동일 Tenant에서 동일 Key·동일 Body를
재요청하면 같은 응답을 `200`으로 반환하고 Case를 추가하지 않는다. 같은 Key를 다른
Body에 사용하면 `409 IDEMPOTENCY_KEY_REUSED`다. Key의 Tenant 범위는 인증 Principal로
결정한다.

### Case 목록 응답

```json
{
  "items": [
    {
      "case_id": "<uuid>",
      "tenant_id": "<uuid>",
      "domain_type": "product_defect_cs",
      "status": "RECEIVED",
      "order_ref": "ORD-2026-0001",
      "product_ref": "SKU-001",
      "requested_action": "EXCHANGE",
      "created_at": "2026-08-26T13:00:00Z",
      "updated_at": "2026-08-26T13:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### Case 상세 응답

상세는 Case 생성 입력과 생성자·시각에 더해 `evidence`, `status_history`를 포함한다.
Sprint 2 서비스가 구성되어 있고 Run이 존재하면 `latest_analysis_run`에 최신 안전한 Run
Projection을 조합한다. Case Row에 분석 상태를 복제하지 않으며 Run이 없으면 `null`이다.

```json
{
  "case_id": "<uuid>",
  "tenant_id": "<uuid>",
  "domain_type": "product_defect_cs",
  "status": "RECEIVED",
  "order_ref": "ORD-2026-0001",
  "product_ref": "SKU-001",
  "customer_message": "용기 하단이 찌그러졌고 내용물이 샜습니다. 교환을 요청합니다.",
  "requested_action": "EXCHANGE",
  "attributes": {"order_amount": 42000, "days_since_purchase": 3},
  "created_by": "<user-uuid>",
  "created_at": "2026-08-26T13:00:00Z",
  "updated_at": "2026-08-26T13:00:00Z",
  "evidence": [],
  "status_history": [
    {
      "history_id": "<uuid>",
      "from_status": null,
      "to_status": "RECEIVED",
      "actor_id": "<user-uuid>",
      "reason": "case_created",
      "occurred_at": "2026-08-26T13:00:00Z"
    }
  ],
  "latest_analysis_run": null
}
```

## 5. Evidence 계약

```http
POST /api/v1/cases/{case_id}/evidence
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

Form 필드:

```text
file=<JPEG, PNG 또는 WebP binary>
evidence_type=IMAGE
```

업로드와 조회의 Evidence 메타데이터 응답:

```json
{
  "evidence_id": "<uuid>",
  "tenant_id": "<uuid>",
  "case_id": "<uuid>",
  "evidence_type": "IMAGE",
  "upload_status": "AVAILABLE",
  "original_filename": "evidence.png",
  "content_type": "image/png",
  "size_bytes": 1234,
  "sha256": "<64-lowercase-hex>",
  "width": 64,
  "height": 64,
  "created_by": "<user-uuid>",
  "created_at": "2026-08-26T13:01:00Z",
  "updated_at": "2026-08-26T13:01:01Z"
}
```

접근 URL은 별도 요청으로만 만든다.

```json
{
  "evidence_id": "<uuid>",
  "url": "<short-lived-presigned-get-url>",
  "expires_at": "2026-08-26T13:16:01Z"
}
```

`url`은 응답 예시·로그·DB에 실제 값을 기록하지 않는다. Bucket은 Private이며 설정된
`SIGNED_URL_TTL_SECONDS`를 사용한다. 응답에는 `Cache-Control: no-store`를 적용한다.
URL 발급 직전에 내부 Storage Endpoint로 Object HEAD를 확인한다. Evidence가 `AVAILABLE`이
아니거나 DB는 `AVAILABLE`이지만 Object가 없으면 `500 EVIDENCE_UPLOAD_FAILED`, HEAD 또는
URL 생성 중 Storage 호출이 실패하면 `503 STORAGE_UNAVAILABLE`을 반환한다.

## 6. Sprint 2 Analysis HTTP API

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/api/v1/cases/{case_id}/analysis-runs` | Admin, Reviewer | 새 Text Analysis Run 등록 |
| GET | `/api/v1/cases/{case_id}/analysis-runs` | 모든 역할 | Tenant/Case 범위 목록·필터·페이지 |
| GET | `/api/v1/cases/{case_id}/analysis-runs/{analysis_run_id}` | 모든 역할 | Run, Stage와 구조화 결과 상세 |

모든 Endpoint는 Bearer 인증을 요구하고 Tenant는 Principal에서 정한다. 현재 Tenant에서 Case를
먼저 찾은 뒤 권한을 검사하며, 다른 Tenant의 Case/Run은 `404`로 숨긴다. 응답에는
`Cache-Control: no-store`, `Pragma: no-cache`와 `X-Correlation-ID`를 적용한다.

목록 Query는 `status`, `pipeline`, `page`(기본 1), `page_size`(기본 20, 1~100)를 받는다.
정렬은 최신 요청 우선이며 목록은 Run Projection만 반환한다. 상세는 Run, Stage Snapshot과
성공한 `extraction_result`를 반환한다. 공개 Projection은 Idempotency Key, Request Hash,
Correlation ID, Claim Token/Lease, 내부 실패 Message와 Provider Request ID를 제외한다.

## 7. Analysis 등록과 Idempotency

```http
POST /api/v1/cases/CASE-2026-0001/analysis-runs
Authorization: Bearer <access-token>
Idempotency-Key: <required-tenant-scoped-key>
Content-Type: application/json
```

```json
{
  "pipeline": "product_defect_text_extraction",
  "pipeline_version": "1.0.0"
}
```

응답:

```json
{
  "analysis_run_id": "AR-2026-0001",
  "tenant_id": "tenant-a",
  "case_id": "CASE-2026-0001",
  "pipeline": "product_defect_text_extraction",
  "pipeline_version": "1.0.0",
  "trigger": "USER_REQUEST",
  "status": "QUEUED",
  "requested_by": "user-a",
  "requested_at": "2026-08-26T13:00:00Z",
  "started_at": null,
  "completed_at": null,
  "failure": null,
  "created_at": "2026-08-26T13:00:00Z",
  "updated_at": "2026-08-26T13:00:00Z"
}
```

새 등록은 `202 Accepted`와 `Location` Header를 반환한다. 동일 Tenant에서 같은 Key와 같은
Case/Pipeline/Version을 재요청하면 기존 Run을 `200 OK`로 재생하고 새 Stage/Outbox를 만들지
않는다. 같은 Key를 다른 정규 요청에 사용하면 `409 IDEMPOTENCY_KEY_REUSED`다. 알 수 없는
Pipeline Enum은 `422 VALIDATION_ERROR`, 지원 Pipeline의 미지원 Version은
`422 ANALYSIS_PIPELINE_NOT_SUPPORTED`다. Terminal Run을 되살리는 공개 Retry API는 Sprint 2에
없다. 재분석은 새 Key로 새 Run을 등록한다.

## 8. Sprint 2 LLM 구조화 결과

Sprint 2.5의 실제 Qwen 배포도 이 계약을 변경하지 않는다. 요청은
`enable_thinking=false`, `preserve_thinking=false`, Temperature 0과 strict JSON Schema를
명시하며, Service Model Name `csight-qwen3.8-27b`와 immutable Artifact revision을 실행
Metadata로 저장한다. Reasoning Field, Schema 밖 Field와 JSON 앞뒤 자연어는 계약 위반이다.

```json
{
  "schema_version": "1.0",
  "language": "ko",
  "issue_types": ["DENT", "LEAKAGE"],
  "claims": [
    {
      "type": "DENT",
      "location": "BOTTOM",
      "description": "용기 하단 찌그러짐 주장",
      "source_quote": "용기 하단이 찌그러졌고"
    }
  ],
  "requested_action": "EXCHANGE",
  "missing_information": [],
  "summary": "고객은 용기 하단 파손과 누액을 이유로 교환을 요청함"
}
```

허용 Issue Taxonomy는 정확히 `DENT`, `CRACK`, `BREAKAGE`, `LEAKAGE`,
`MISSING_COMPONENT`, `WRONG_ITEM`, `CONTAMINATION`, `FUNCTIONAL_FAILURE`,
`PACKAGING_DAMAGE`, `OTHER`, `UNKNOWN`이다. Claim은 `type`, `location`, `description`과
선택적 `source_quote`를 가진다. Quote가 있으면 고객 원문의 정확한 연속 부분 문자열이어야
한다. 추가 Field, 중복 Enum, Claim에만 존재하는 Issue Type과 Character 상한 초과는
저장 전에 거부한다.

Location은 `TOP`, `BOTTOM`, `SIDE`, `FRONT`, `BACK`, `INSIDE`, `OUTSIDE`, `MULTIPLE`,
`UNKNOWN` 중 하나다. Missing Information은 `PRODUCT_REFERENCE`, `ORDER_REFERENCE`,
`DEFECT_TYPE`, `DEFECT_LOCATION`, `CUSTOMER_REQUEST`, `IMAGE_EVIDENCE`,
`ADDITIONAL_DESCRIPTION`만 허용한다. `language`는 2~3자 소문자 언어 코드와 선택적 대문자
지역 코드 형식을 사용한다.

`requested_action`은 `REFUND`, `EXCHANGE`, `RESHIPMENT`, `REPAIR`, `INFORMATION`, `OTHER`,
`UNKNOWN` 중 하나다. 이는 고객 문장에서 추출한 요청이지 환불·교환 승인이나 최종 Decision이
아니다. Vision 출력은 Sprint 3 이후 계약이며 Sprint 2 상세 응답에 포함되지 않는다.

## 9. `analysis.requested.v1` Event 계약

PostgreSQL Outbox Payload는 감사와 검증을 위해 Event Type/Version/발생 시각도 보존한다.
Dispatcher가 RabbitMQ/Celery에 전달하는 Queue Payload는 다음 여섯 식별자만 포함한다.

```json
{
  "event_id": "EVT-001",
  "tenant_id": "tenant-a",
  "case_id": "CASE-2026-0001",
  "analysis_run_id": "AR-2026-0001",
  "stage_run_id": "STAGE-001",
  "correlation_id": "CORR-001"
}
```

고객 원문, 주문·상품 값, Evidence ID/Binary, Prompt, Raw Provider Response, JWT, Signed URL과
Secret은 Broker Payload에 넣지 않는다. Worker가 여섯 ID로 DB에서 allowlisted Case 입력을
다시 읽는다. 활성 Stage Lease 중 중복 Delivery가 오면 Lease 만료 시각에 사용할 동일한 여섯
ID 형식의 Recovery Event 하나를 Outbox에 저장한다. 기존 Worker가 완료하면 후속 Delivery는
No-op이고, 그렇지 않으면 만료 Lease 회수 후 재실행한다. Celery Retry는 업무 상태의 Source of
Truth가 아니다. `analysis.completed.v1`, `analysis.failed.v1`, SSE Event는 Sprint 2에 구현되지
않았다.

## 10. 후속 HTTP/Event 범위

Vision, Alignment, Policy, Routing, Human Review, Report와 RAG API, Terminal Run Retry API,
SSE 상태 Event는 Sprint 3 이후 Backlog다. 현재 OpenAPI 계약으로 간주하지 않는다.

## 11. 표준 오류 응답

```json
{
  "error": {
    "code": "CASE_NOT_FOUND",
    "message": "The requested case was not found.",
    "details": {},
    "correlation_id": "CORR-001"
  }
}
```

## 12. HTTP 오류 매핑

| HTTP | 코드 | 의미 |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED` | Bearer Token 누락·만료·무효 또는 현재 계정 비활성 |
| 401 | `INVALID_CREDENTIALS` | 로그인 식별자 또는 비밀번호 오류 |
| 403 | `FORBIDDEN` | 현재 역할에 작업 권한 없음 |
| 404 | `CASE_NOT_FOUND` | 현재 Tenant 범위에서 Case를 찾을 수 없음 |
| 404 | `EVIDENCE_NOT_FOUND` | 현재 Case/Tenant 범위에서 Evidence를 찾을 수 없음 |
| 404 | `ANALYSIS_RUN_NOT_FOUND` | 현재 Case/Tenant 범위에서 Analysis Run을 찾을 수 없음 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 같은 범위의 Key를 다른 Body에 사용 |
| 413 | `FILE_TOO_LARGE` | 설정된 업로드 크기 초과 |
| 422 | `EMPTY_FILE` | 빈 업로드 |
| 422 | `INVALID_FILE_TYPE` | MIME·확장자·실제 형식 불허 또는 불일치 |
| 422 | `INVALID_IMAGE_CONTENT` | 실제 이미지 Decode 실패 |
| 422 | `IMAGE_DIMENSION_LIMIT_EXCEEDED` | 설정된 Pixel 수 초과 |
| 422 | `VALIDATION_ERROR` | Body, Query, Header 또는 Form 검증 실패 |
| 422 | `ANALYSIS_PIPELINE_NOT_SUPPORTED` | 지원하지 않는 Pipeline 또는 Version |
| 500 | `EVIDENCE_UPLOAD_FAILED` | Evidence 저장/상태 확정 실패 |
| 500 | `INCONSISTENT_PERSISTENCE_STATE` | Idempotency 레코드가 없는 Case를 참조 |
| 503 | `STORAGE_UNAVAILABLE` | MinIO 작업 실패 |

`401` 응답에는 `WWW-Authenticate: Bearer`, 모든 응답에는 `X-Correlation-ID`를 포함한다.

## 13. Contract Test 항목

- 필수 필드 누락
- Enum 불일치
- 좌표 범위 0~1 검증
- 모델 버전 누락
- Schema Version 불일치
- Timeout 및 재시도
- 동일 Idempotency Key 재요청
- Analysis 등록의 필수 Idempotency Key, 새 요청 `202`와 동일 요청 재생 `200`
- Analysis 등록 권한과 Tenant/Case-scoped 목록·상세 `404`
- Run/Stage Terminal 전이와 Fenced 중복 완료 No-op
- Outbox DB Payload와 정확히 여섯 ID인 Queue Payload 구분
- LLM Issue Taxonomy, 추가 Field 거부와 정확한 `source_quote` 부분 문자열
- Prompt Injection 입력을 명령이 아닌 JSON-escaped 데이터로 취급
- Case 생성 요청의 `tenant_id` 거부
- 새 Case `201`과 동일 요청 재생 `200` 구분
- 역할별 `401`/`403`과 다른 Tenant의 `404`
- 목록에서 고객 원문과 Signed URL 제외
- Multipart `IMAGE`와 실제 JPEG/PNG/WebP 검증
- Signed URL 응답의 만료와 Tenant Scope
- Vision class mapping 변경은 Sprint 3 계약 범위
- LLM 비정상 JSON, 추가 자연어, 입력·출력 상한 초과

관련 결정은 [ADR-0009](adr/0009-transactional-outbox-and-fenced-analysis-execution.md),
[ADR-0010](adr/0010-code-prompt-registry-and-structured-output-retention.md),
[ADR-0011](adr/0011-separate-case-and-analysis-lifecycles.md)을 따른다.

## 14. Sprint 3 Multimodal API와 Vision Contract

기존 `POST /api/v1/cases/{case_id}/analysis-runs`에서 아래 body를 추가 지원한다.

```json
{"pipeline":"product_defect_multimodal_analysis","pipeline_version":"1.0.0"}
```

AVAILABLE Image가 없으면 `422 IMAGE_EVIDENCE_REQUIRED`다. Text-only body와 의미는 그대로다.
상세 응답은 `vision_results`와 `failed_stages`를 추가하며 각 Vision Result는 evidence 한 건에
대응한다. `PARTIAL_SUCCESS`에서도 성공한 `extraction_result` 또는 `vision_results`를 반환한다.

Remote Vision 계약은 private `POST /v1/vision/analyze`, multipart `file`과
`task=product_defect_detection`이다. Adapter는 응답을 schema `1.0`, tri-state image quality,
canonical label, confidence, `normalized_xyxy` bbox와 version metadata로 검증한다. 429/5xx와
transport timeout은 retryable, 400/401/403/schema/geometry 오류는 permanent다.

Image-level binary mode uses the same private endpoint with
`task=product_defect_any_defect_classification`. The provider response retains its own score and
frozen threshold:

```json
{
  "schema_version": "1.0",
  "provider": {
    "model_name": "dinov2-any-defect",
    "model_version": "e3-epoch-10",
    "model_revision": "<packaged-checkpoint-revision>",
    "dataset_version": "<dataset-manifest-version>",
    "taxonomy_version": "kaputt-any-defect-binary-v1",
    "threshold_version": "<frozen-threshold-version>",
    "preprocess_version": "<preprocess-version>",
    "postprocess_version": "<postprocess-version>"
  },
  "image_quality": {"usable": "NOT_EVALUATED"},
  "image_assessment": {
    "label": "defect",
    "score": 0.95,
    "threshold": 0.8984375
  },
  "detections": []
}
```

Core verifies that the returned threshold matches `VISION_ASSESSMENT_EXPECTED_THRESHOLD`, derives
the comparison outcome, and exposes the following additive field inside each `vision_results[].result`:

```json
{
  "image_assessment": {
    "assessment_type": "ANY_DEFECT",
    "model_output_name": "defect",
    "score": 0.95,
    "threshold": 0.8984375,
    "threshold_operator": "GREATER_THAN_OR_EQUAL",
    "outcome": "HIGH_CONFIDENCE_DEFECT_CANDIDATE"
  },
  "detections": []
}
```

The only other outcome is `BELOW_HIGH_CONFIDENCE_THRESHOLD`; it does not mean `NORMAL`. Binary
responses containing a Detection, missing an assessment, or returning a different threshold are
permanent structured-output failures. Existing `product_defect_detection` request and response
shapes remain compatible.

Queue payload는 Sprint 2와 같은 event/tenant/case/run/stage/correlation ID 6개뿐이다. Evidence
ID 목록, object key, Binary, Base64, Signed URL과 credential은 포함하지 않는다.

## 15. Text Extraction v2 API

기존 endpoint에 `{"pipeline":"product_defect_text_extraction","pipeline_version":"2.0.0"}`을
추가 지원한다. v1 상세은 기존 `extraction_result` 형태를 유지한다. v2 상세은
`extraction_result_v2`에 schema version, requested action list, text ambiguity, deterministic
system missing/action consistency와 completeness rule version을 명시한다. Queue event는 기존
6-ID 계약을 변경하지 않는다.

## 16. Policy Retrieval API

`POST /api/v1/policy-retrieval/search`는 읽기 권한 세 역할에 LEXICAL/DENSE/HYBRID 검색을 제공한다.
Query 2–2000자, top_k 1–20, mode/filter allowlist를 검증한다. Tenant는 JWT principal에서만 오며
response는 clause, version/effective metadata와 rank/score만 포함한다. Provider/index 장애는 각각
`503 EMBEDDING_PROVIDER_UNAVAILABLE`/`POLICY_INDEX_UNAVAILABLE`이다.

`HYBRID_RERANKED`는 같은 endpoint에 명시적으로 추가된다. Hit은 `candidate_rank`, `rerank_rank`,
`rerank_score`, `reranker_profile`을 포함한다. Client는 candidate K/model/profile을 선택하지 못한다.
Reranker 장애는 `503 RERANKER_PROVIDER_UNAVAILABLE`이며 silent fallback과 decision field는 없다.

## Case policy retrieval runs

`POST /api/v1/cases/{case_id}/policy-retrieval-runs` requires Idempotency-Key and returns 202 or replay
200. List and detail GET endpoints are tenant scoped. The broker message is
`policy_retrieval.requested.v1` and contains exactly event, tenant, Case, run, and correlation IDs.

## Sprint 4C-3A Grounded Explanation Contract

`POST/GET /api/v1/cases/{case_id}/grounded-explanation-runs`는 성공한 retrieval run ID만 받아
`202` 비동기 실행을 생성하고 List/Get을 제공한다. Queue payload는 event, tenant, Case,
grounded-run, correlation ID만 포함한다. 응답은 내부 clause row ID와 tenant를 노출하지 않는다.

Local MLX도 기존 Analysis/Retrieval/Grounding API와 identifier-only event를 그대로 사용한다.
Provider metadata는 `mlx`, local served-name, version/revision, prompt hash를 기록하되 host cache
path와 raw prompt/response/reasoning은 공개하거나 저장하지 않는다.

## Sprint 5A Policy Evaluation API

`POST/GET /api/v1/cases/{case_id}/policy-evaluation-runs`와 `GET .../{run_id}`를 제공한다.
POST body는 `analysis_run_id`, `as_of_date`만 받으며 tenant/rule-set은 Core가 선택한다. 새 요청은
202, replay는 200, key 충돌은 409다. Queue에는 event/tenant/case/evaluation-run/correlation ID만
들어가며 rule JSON, 분석 JSON, 고객 원문, JWT는 들어가지 않는다.
# Sprint 5B API and event contracts

`GET /api/v1/human-review-tasks` and task/case detail routes are readable by all current roles.
Claim, release, evidence request, resume, escalate, and resolve routes require human-review action
permission. Resolve is the only final-decision creator. The queue event contains only event, tenant,
case, policy evaluation, and correlation IDs.

## Sprint 5C Resolution, report, and metric contracts

Authenticated read-only endpoints:

| Method | Path | Contract |
|---|---|---|
| `GET` | `/api/v1/cases/{case_id}/resolution` | Current versioned Resolution projection |
| `GET` | `/api/v1/cases/{case_id}/resolution/events` | Ordered append-only Events |
| `GET` | `/api/v1/cases/{case_id}/external-action-intents` | Immutable typed Intent summaries |
| `GET` | `/api/v1/external-action-intents/{intent_id}` | Intent with safe Attempt/Result projections |
| `GET` | `/api/v1/cases/{case_id}/review-report` | Latest immutable terminal `review_report/1.0.0` |
| `GET` | `/api/v1/metrics/poc-summary` | Seven tenant-scoped KPI aggregates |

The two queues use exact five-field identifier envelopes:

- `case_resolution.requested.v1`: `event_id`, `tenant_id`, `case_id`, `resolution_id`,
  `correlation_id`;
- `external_action.simulation_requested.v1`: `event_id`, `tenant_id`, `case_id`,
  `external_action_intent_id`, `correlation_id`.

Public responses never expose tenant IDs, dispatcher claims, execution tokens, leases, JWTs, or
credentials. There is no Resolution write endpoint, input-completion endpoint, Case-close endpoint,
or LIVE external-action endpoint. Report and KPI responses are `no-store`; KPI fields each include
`numerator`, `denominator`, `sample_count`, `value`, and `unit`.

## Operator queue and workflow read contracts

The Core API owns the operator queue projection; the browser does not fan out into per-Case detail
requests. All three endpoints require `HUMAN_REVIEW_READ`, derive the tenant and current actor from
the authenticated Principal, perform no provider calls, and return `Cache-Control: no-store`.

| Method | Path | Contract |
|---|---|---|
| `GET` | `/api/v1/operator/cases` | Case work queue plus view counts |
| `GET` | `/api/v1/operator/reviews` | Human Review task queue plus view counts |

Both operator queue endpoints accept `view`, `sort`, opaque `cursor`, bounded
`limit`, and an optional `q` (maximum 100 characters). Search is executed in the
same tenant-scoped SQL projection across inquiry/case ID, order reference, and
product reference (plus review-task ID for the review queue); wildcard characters
are treated literally. Returned counts reflect the active search and cursors are
hash-bound to the normalized search text, so an unchanged cursor is rejected
after the query changes.
| `GET` | `/api/v1/cases/{case_id}/workflow-snapshot` | Persisted workflow status projection |

Queue query parameters are `view`, `sort`, `limit`, and `cursor`. `view` is one of `all`, `my`,
`unassigned`, `urgent`, `waiting_evidence`, or `complete`; `sort` is `newest` or `oldest`; and
`limit` is 1 through 100. Pagination uses an opaque, versioned keyset cursor bound to the endpoint,
view, and sort. A malformed or cross-view cursor returns `422 VALIDATION_ERROR`.

`my` means a `CLAIMED` or `WAITING_FOR_EVIDENCE` task assigned to the current actor. `unassigned` means an unassigned
`PENDING` or `ESCALATED` task. `urgent` means an active `HIGH` or `CRITICAL` task.
`waiting_evidence` means `WAITING_FOR_EVIDENCE`. For the Case queue, `complete` means that an
immutable Review Report exists; for the Review queue, it means that the task is `RESOLVED`.
`counts` contains all six view totals over the unpaginated tenant scope and is returned in the same
database statement as the page. Queue responses omit the customer message, Case attributes,
Evidence locations, tokens, claims, leases, and provider payloads.

The workflow snapshot selects the latest persisted Analysis, Policy Retrieval, Grounded
Explanation, Policy Evaluation, and Human Review records, the current Resolution, and the latest
Review Report. `terminal=true` only when an immutable Review Report exists. `degraded=true` reports
persisted partial/failure/manual-follow-up states. `retry_at` is the earliest persisted retry time
of the latest Analysis run, `last_good` is the downstream-most successfully persisted boundary,
and `correlation_id` is the downstream-most available persisted correlation ID. These fields are a
read projection only: they do not advance a workflow, resolve a task, create a decision, or perform
an external action.

## Limited-pilot authentication contracts

| Method | Path | Contract |
|---|---|---|
| `GET` | `/auth/oidc/login` | Start one-time Authorization Code + PKCE flow for an allowlisted return path |
| `GET` | `/auth/oidc/callback` | Validate code/state/nonce and set an opaque HttpOnly session cookie |
| `GET` | `/auth/session` | Rotate the memory-only CSRF proof and return current Principal and expiry |
| `POST` | `/auth/logout` | Validate CSRF, revoke the hashed server session, and expire the cookie |
| `POST` | `/auth/oidc/backchannel-logout` | Validate a signed provider logout token and idempotently revoke matching active sessions |

Unsafe `/api` requests authenticated by the OIDC cookie require `X-CSRF-Token`. The response never
contains an IdP access/refresh token. `POST /api/v1/auth/token` exists only when the explicit
local/test compatibility profile enables it. Pilot and production processes omit the route from routing and
OpenAPI, advertise `legacy_password_enabled=false`, and reject Bearer JWT on protected APIs.
The back-channel route accepts form-encoded `logout_token` only in an OIDC-configured process. It returns
`200` for the first receipt and a replay of the same JWT ID, `400` for an invalid signed token, and `503` when
validation or persistence is temporarily unavailable. It never accepts browser session authentication or
creates an external business action.

## Admin operations read contracts

| Method | Path | Contract |
|---|---|---|
| `GET` | `/api/v1/operations/overview` | Bounded Queue/component backlog and recent version aggregates |
| `GET` | `/api/v1/operations/failures` | Bounded failure, partial, retry, and stalled summaries |

Both endpoints require the current tenant's `ADMIN` role, execute one tenant-scoped SQL statement,
return `no-store`, and omit tenant/Case/run/Event identifiers and raw error text. Replay and cancel
routes are not enabled: their immutable recovery-operation identity, idempotency, live-claim
fencing, and append-only audit contract remain a pilot activation blocker.
## Case assignment contract

- `GET /api/v1/cases/{case_id}/assignment` returns the current assignment projection and version.
- `POST /api/v1/cases/{case_id}/assignment` is administrator-only and accepts `assignee_id`,
  `expected_version`, and `rationale`. Stale versions return `409`; ineligible users and terminal
  Cases fail closed.
- `GET /api/v1/operator/cases` includes `assignment_version` without per-row detail requests.
- Reviewer access to Case-scoped detail APIs returns `404` unless the Case is currently assigned to
  that reviewer or was finalized by that reviewer.

## Signed model release contracts

| Method | Path | Contract |
|---|---|---|
| `POST` | `/api/v1/operations/model-releases` | Verify and immutably register an exact release-eligible signed manifest |
| `POST` | `/api/v1/operations/model-releases/{release_id}/activate` | Append a PRIMARY/SHADOW activation or rollback event using `Idempotency-Key` and expected-current CAS |
| `GET` | `/api/v1/operations/model-activations/active` | Read the latest activation and signed release for one task/mode |

All three are admin-only, tenant-scoped, and `no-store`. Registration does not sign a manifest or
override its qualification status, and activation performs no external business action.

## Pilot metric source scope

`GET /api/v1/metrics/poc` returns `eligible_source_scope=PILOT_LIVE`, `eligible_case_count`, and
`excluded_case_count`. Every metric denominator uses eligible Cases only. `GET /api/v1/data-assets/summary`
returns total, eligible, excluded, and per-scope counts; readiness, distributions, and recent records use only
eligible assets. Synthetic, Shadow, imported, and unattested records never contribute to the default KPI, SLA,
or drift-readiness contract.

## Signed Case intake contract

`POST /api/v1/integrations/cases` is available only in an explicitly configured signed-intake deployment.
`X-CSight-Intake-Key-Id`, `X-CSight-Intake-Event-Id`, `X-CSight-Intake-Timestamp`, and
`X-CSight-Intake-Signature` authenticate the exact raw JSON bytes using ADR-0120's Ed25519 canonical form.
The body uses `signed_case_intake/1.0.0` and cannot contain `tenant_id` or `source_scope`. A valid first delivery
returns `201` and a `PILOT_LIVE` Case; an exact source-event replay returns `200` with the same Case; a changed
payload under the same event returns `409`. Invalid or stale authentication returns a generic `401` with zero
writes. The endpoint does not accept attachments or initiate analysis, review, resolution, or external action.

## Pilot readiness contract

`GET /api/v1/operations/pilot-readiness` is admin-only and returns `configuration_ready`,
`operationally_qualified`, `pilot_ready`, and the combined configuration and qualification gate list.
Each gate contains a bounded code, status, description, verification/expiry timestamps, and optional
PII-free evidence digest. Tenant, Case, user, source identifiers, raw input, secrets, and filesystem
paths are excluded. Missing or expired operational evidence is `FAIL`, and the response is `no-store`.

The separately generated `docs/openapi/pilot.openapi.json` includes the signed Case intake and pilot
readiness routes. It is an activation artifact only; generating it does not enable signed intake or
admit a tenant.
