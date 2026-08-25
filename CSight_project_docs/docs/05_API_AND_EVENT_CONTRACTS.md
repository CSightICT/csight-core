# 05. API and Event Contracts

## 1. 계약 원칙

- 외부 API는 `/api/v1`으로 버전 관리한다.
- Sprint 1의 Case 생성과 Evidence 업로드는 동기 요청이다. 새 리소스는 `201 Created`,
  Case Idempotency 재생은 `200 OK`를 반환한다.
- 장시간 분석 요청은 Sprint 2부터 `202 Accepted`를 반환한다.
- Sprint 1은 Case 생성에만 `Idempotency-Key`를 지원한다. Evidence 업로드 Idempotency는
  후속 범위다.
- Event와 모델 출력에는 `schema_version`을 포함한다.
- 모델 고유 출력은 외부에 직접 노출하지 않고 공통 Schema로 변환한다.
- 원본 AI 결과와 정규화 결과를 구분해 저장할 수 있다.
- 모든 Case·Evidence API는 Bearer 인증을 요구한다. `tenant_id`는 입력으로 받지 않고
  현재 Principal에서 결정한다.
- 요청 Schema는 알 수 없는 필드를 거부한다. 따라서 Body에 `tenant_id`를 넣으면
  `422 VALIDATION_ERROR`다.
- 날짜·시각은 UTC Offset을 포함한 RFC 3339 형식을 사용하고 ID는 불투명 문자열로
  취급한다.

## 2. Sprint 1 HTTP API

### 인증

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/v1/auth/token` | 불필요 | 로컬·PoC Access Token 발급 |
| GET | `/api/v1/auth/me` | Bearer | 현재 사용자, Tenant와 현재 역할 조회 |

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
Sprint 1은 Analysis Run을 만들지 않으므로 `latest_analysis_run`은 `null`이다.

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

## 6. Sprint 2 이후 HTTP API 목표

아래 API는 설계 목표이며 Sprint 1 구현/OpenAPI에는 포함되지 않는다.

| 영역 | Method | Path | 설명 |
|---|---|---|---|
| Analysis | POST | `/api/v1/cases/{case_id}/analysis-runs` | 분석 작업 등록, `202` |
| Analysis | GET | `/api/v1/analysis-runs/{run_id}` | 분석 상태·결과 조회 |
| Analysis | POST | `/api/v1/analysis-runs/{run_id}/retry` | 실패 작업 재시도 |
| Event | GET | `/api/v1/cases/{case_id}/events` | SSE 상태 이벤트 |
| Policy | POST | `/api/v1/policies` | 정책 생성 |
| Policy | POST | `/api/v1/policies/{policy_id}/versions` | 새 버전 생성 |
| Policy | GET | `/api/v1/policies/active` | 활성 정책 조회 |
| Review | POST | `/api/v1/cases/{case_id}/reviews` | 승인·수정·이관 저장 |
| Review | GET | `/api/v1/cases/{case_id}/reviews` | Review 이력 조회 |
| Report | POST | `/api/v1/cases/{case_id}/reports` | 검토 보고서 생성 요청 |
| Report | GET | `/api/v1/reports/{report_id}` | 보고서 조회 |

## 7. 분석 등록 목표 예시

```http
POST /api/v1/cases/CASE-2026-0001/analysis-runs
Idempotency-Key: 0192f-example
```

```json
{
  "domain": "product_defect_cs",
  "llm_profile": "default-extraction",
  "vision_profile": "defect-detector-v1",
  "policy_mode": "ACTIVE_VERSION"
}
```

응답:

```json
{
  "analysis_run_id": "AR-2026-0001",
  "status": "QUEUED"
}
```

## 8. LLM 공통 출력

```json
{
  "schema_version": "1.0",
  "model": {
    "provider": "vllm",
    "name": "configured-model",
    "version": "deployment-version"
  },
  "issue_type": "LEAKAGE",
  "claimed_location": "BOTTOM",
  "customer_request": "EXCHANGE",
  "claims": [
    {
      "type": "CONTAINER_DAMAGE",
      "description": "용기 하단이 찌그러졌다고 주장함"
    },
    {
      "type": "LEAKAGE",
      "description": "내용물이 외부로 누출되었다고 주장함"
    }
  ],
  "missing_information": [],
  "summary": "고객은 용기 하단 파손과 누액을 이유로 교환을 요청함"
}
```

## 9. Vision 공통 출력

```json
{
  "schema_version": "1.0",
  "model": {
    "provider": "remote-vision",
    "name": "csight-defect-detector",
    "version": "0.1.0",
    "preprocess_version": "1.0"
  },
  "image_quality": {
    "blurred": false,
    "too_dark": false,
    "product_visible": true,
    "defect_area_visible": true,
    "score": 0.94
  },
  "detections": [
    {
      "label": "LEAKAGE",
      "confidence": 0.87,
      "geometry": {
        "type": "BOUNDING_BOX",
        "coordinate_system": "NORMALIZED",
        "x1": 0.31,
        "y1": 0.48,
        "x2": 0.76,
        "y2": 0.91
      }
    }
  ],
  "latency_ms": 52
}
```

## 10. Event 계약

### `analysis.requested.v1`

```json
{
  "event_id": "EVT-001",
  "event_type": "analysis.requested.v1",
  "occurred_at": "2026-08-25T13:01:00Z",
  "tenant_id": "tenant-a",
  "case_id": "CASE-2026-0001",
  "analysis_run_id": "AR-2026-0001",
  "correlation_id": "CORR-001",
  "evidence_ids": ["EVID-001"]
}
```

### `analysis.completed.v1`

```json
{
  "event_id": "EVT-002",
  "event_type": "analysis.completed.v1",
  "case_id": "CASE-2026-0001",
  "analysis_run_id": "AR-2026-0001",
  "decision": "HUMAN_REVIEW_REQUIRED",
  "completed_at": "2026-08-25T13:01:08Z"
}
```

### `analysis.failed.v1`

```json
{
  "event_id": "EVT-003",
  "event_type": "analysis.failed.v1",
  "case_id": "CASE-2026-0001",
  "analysis_run_id": "AR-2026-0001",
  "failure_stage": "VISION_INFERENCE",
  "retryable": true,
  "error_code": "VISION_TIMEOUT"
}
```

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
| 409 | `IDEMPOTENCY_KEY_REUSED` | 같은 범위의 Key를 다른 Body에 사용 |
| 413 | `FILE_TOO_LARGE` | 설정된 업로드 크기 초과 |
| 422 | `EMPTY_FILE` | 빈 업로드 |
| 422 | `INVALID_FILE_TYPE` | MIME·확장자·실제 형식 불허 또는 불일치 |
| 422 | `INVALID_IMAGE_CONTENT` | 실제 이미지 Decode 실패 |
| 422 | `IMAGE_DIMENSION_LIMIT_EXCEEDED` | 설정된 Pixel 수 초과 |
| 422 | `VALIDATION_ERROR` | Body, Query, Header 또는 Form 검증 실패 |
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
- Case 생성 요청의 `tenant_id` 거부
- 새 Case `201`과 동일 요청 재생 `200` 구분
- 역할별 `401`/`403`과 다른 Tenant의 `404`
- 목록에서 고객 원문과 Signed URL 제외
- Multipart `IMAGE`와 실제 JPEG/PNG/WebP 검증
- Signed URL 응답의 만료와 Tenant Scope
- Vision class mapping 변경
- LLM 비정상 JSON 및 추가 자연어 포함
