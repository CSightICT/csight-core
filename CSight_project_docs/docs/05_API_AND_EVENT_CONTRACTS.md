# 05. API and Event Contracts

## 1. 계약 원칙

- 외부 API는 `/api/v1`으로 버전 관리한다.
- 장시간 분석 요청은 `202 Accepted`를 반환한다.
- 생성·분석 요청은 `Idempotency-Key`를 지원한다.
- Event와 모델 출력에는 `schema_version`을 포함한다.
- 모델 고유 출력은 외부에 직접 노출하지 않고 공통 Schema로 변환한다.
- 원본 AI 결과와 정규화 결과를 구분해 저장할 수 있다.

## 2. HTTP API 초안

### Case

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/cases` | Case 생성 |
| GET | `/api/v1/cases/{case_id}` | Case 상세 조회 |
| GET | `/api/v1/cases` | 필터·페이지 기반 목록 조회 |
| POST | `/api/v1/cases/{case_id}/evidence` | Evidence 추가 |
| GET | `/api/v1/cases/{case_id}/events` | SSE 상태 이벤트 |

### Analysis

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/cases/{case_id}/analysis-runs` | 분석 작업 등록 |
| GET | `/api/v1/analysis-runs/{run_id}` | 분석 상태·결과 조회 |
| POST | `/api/v1/analysis-runs/{run_id}/retry` | 실패 작업 재시도 |

### Policy

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/policies` | 정책 생성 |
| POST | `/api/v1/policies/{policy_id}/versions` | 새 버전 생성 |
| GET | `/api/v1/policies/active` | Case 조건에 맞는 활성 정책 조회 |

### Review

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/cases/{case_id}/reviews` | 승인·수정·이관 저장 |
| GET | `/api/v1/cases/{case_id}/reviews` | Review 이력 조회 |

### Report

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/cases/{case_id}/reports` | 검토 보고서 생성 요청 |
| GET | `/api/v1/reports/{report_id}` | 보고서 조회 |

## 3. Case 생성 예시

```json
{
  "tenant_id": "tenant-a",
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
  "case_id": "CASE-2026-0001",
  "status": "RECEIVED",
  "created_at": "2026-08-25T13:00:00Z"
}
```

## 4. 분석 등록 예시

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

## 5. LLM 공통 출력

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

## 6. Vision 공통 출력

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

## 7. Event 계약

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

## 8. 표준 오류 응답

```json
{
  "error": {
    "code": "CASE_NOT_FOUND",
    "message": "요청한 Case를 찾을 수 없습니다.",
    "details": {},
    "correlation_id": "CORR-001"
  }
}
```

## 9. Contract Test 항목

- 필수 필드 누락
- Enum 불일치
- 좌표 범위 0~1 검증
- 모델 버전 누락
- Schema Version 불일치
- Timeout 및 재시도
- 동일 Idempotency Key 재요청
- Vision class mapping 변경
- LLM 비정상 JSON 및 추가 자연어 포함
