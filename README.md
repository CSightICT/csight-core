# CSight

> 이미지·텍스트 기반 상품 불량 CS 의사결정 지원 플랫폼

이 저장소는 CSight의 **Sprint 3 Vision Analysis & Multimodal Slice**입니다. Python 3.12,
FastAPI, SQLAlchemy 2/Alembic, Celery/RabbitMQ, PostgreSQL/pgvector, MinIO를 사용하며,
API와 Worker는 같은 이미지에서 서로 다른 프로세스로 실행됩니다.

Sprint 1의 JWT, Tenant 격리, Case와 Private Evidence 기능 위에 Analysis Run·Stage·Attempt,
Transactional Outbox, 얇은 Celery Worker, 버전 고정 Prompt Registry, Text/Vision Provider,
Evidence Snapshot과 append-only image result를 제공합니다. Analysis는 명시적 `202 Accepted`
요청으로만 시작하며 Case 상태를 변경하지 않습니다. LLM과 Vision은 Evidence 분석만 수행하고
정책 판정, 승인, Alignment, Routing, Human Review, RAG와 Report는 포함하지 않습니다.
설계 문서, Accepted ADR과 SVG 자산은
[`CSight_project_docs/`](CSight_project_docs/)에서 함께 관리합니다.

## 빠른 시작

필수 도구:

- Docker Desktop과 Docker Compose
- [`uv`](https://docs.astral.sh/uv/) (호스트 품질 검사와 테스트용)
- `curl`; 아래 API 예시의 응답 추출에는 `jq`

프로젝트 루트에서 다음 명령을 실행합니다.

```bash
cp .env.example .env
uv sync --frozen --group dev
make up
make migrate
make seed
```

`make up`은 이미지를 빌드하고 PostgreSQL, RabbitMQ, MinIO, Bucket 초기화, API,
Worker와 Outbox Dispatcher를 시작한 뒤 Health Check를 기다립니다. 모든 외부 포트는 `127.0.0.1`에만
바인딩됩니다.

시작하기 전에 `.env`에서 다음 값을 직접 설정합니다.

- `JWT_SECRET_KEY`: Local 전용 무작위 값, 최소 32바이트
- `DEVELOPMENT_SEED_ENABLED=true`
- `DEVELOPMENT_SEED_ADMIN_PASSWORD`: 12자 이상
- `DEVELOPMENT_SEED_REVIEWER_PASSWORD`: 12자 이상
- `DEVELOPMENT_SEED_QUALITY_VIEWER_PASSWORD`: 12자 이상
- PostgreSQL, RabbitMQ, MinIO의 Local Credential

저장소에는 실제 Secret을 추가하지 않습니다. `make seed`는 자동 실행되지 않으며
`ENVIRONMENT=local` 또는 `test`이고 위 Guard가 충족될 때만 동작합니다. 반복 실행해도 같은
개발 Identity를 중복 생성하거나 기존 Password Hash를 바꾸지 않습니다.

정상 상태를 확인합니다.

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsS http://127.0.0.1:8000/api/v1/system/info
```

예상 응답은 각각 다음 형태입니다.

```json
{"status":"ok","service":"csight-core-api"}
{"status":"ok","service":"csight-core-api","dependencies":{"postgresql":"ok","rabbitmq":"ok","minio":"ok"}}
{"service":"csight-core-api","version":"0.1.0","environment":"local","api_schema_version":"1.0"}
```

종료할 때는 Named Volume을 보존한 채 서비스를 내립니다.

```bash
make down
```

## 개발 명령

| 목적 | 명령 |
|---|---|
| Core 환경 시작 | `make up` |
| Core 환경 종료 | `make down` |
| 로그 확인 | `make logs` |
| Migration 적용 | `make migrate` |
| Local/Test Identity Seed | `make seed` |
| Outbox 1회 Dispatch | `make outbox` |
| Ruff Lint | `make lint` |
| Ruff Format 검사 | `make format-check` |
| Pyright Type Check | `make typecheck` |
| CI-safe 테스트 | `make test` |
| Core 통합 테스트 | `make test-integration` |
| 전체 로컬 테스트 | `make test-all` |
| Analysis 집중 테스트 | `make test-analysis` |
| Analysis PostgreSQL 통합 | `make test-analysis-integration` |
| Mock Analysis HTTP Smoke | `make smoke-analysis` |
| 선택적 외부 vLLM | `make test-external-llm` |
| 선택적 외부 Vision | `make test-external-vision` |

`make test`는 Docker 인프라와 GPU를 요구하지 않습니다. `make test-integration`과
`make test-all`은 먼저 `make up`과 `make migrate`를 실행한 상태에서 사용합니다.
외부 GPU/서비스 테스트는 `external_gpu`, `external_vision` Marker로 격리되며 기본 명령에서
실행되지 않습니다.
`make smoke-analysis`는 Seed된 Reviewer와 실행 중인 API·Dispatcher·Worker를 사용하며 합성
Case만 생성합니다.

## Sprint 1 API 흐름

Seed가 만드는 Tenant와 사용자는 다음과 같습니다. 비밀번호는 `.env`에 주입한 각 역할별
값을 사용합니다.

| 구분 | 값 |
|---|---|
| Tenant Slug | `csight-demo` |
| Admin | `admin@csight.demo` |
| Reviewer | `reviewer@csight.demo` |
| Quality Viewer | `viewer@csight.demo` |

아래 예시는 Secret과 Token을 출력하지 않고 Shell 변수에 보관합니다.

```bash
read -r -s CSIGHT_LOGIN_PASSWORD
export CSIGHT_LOGIN_PASSWORD

CSIGHT_LOGIN_RESPONSE="$(
  jq -n \
    --arg tenant_slug 'csight-demo' \
    --arg email 'reviewer@csight.demo' \
    --arg password "$CSIGHT_LOGIN_PASSWORD" \
    '{tenant_slug: $tenant_slug, email: $email, password: $password}' |
    curl -fsS http://127.0.0.1:8000/api/v1/auth/token \
      -H 'Content-Type: application/json' \
      --data-binary @-
)"
unset CSIGHT_LOGIN_PASSWORD
CSIGHT_ACCESS_TOKEN="$(printf '%s' "$CSIGHT_LOGIN_RESPONSE" | jq -r '.access_token')"
unset CSIGHT_LOGIN_RESPONSE

curl -fsS http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq
```

Case를 생성합니다. `tenant_id`는 Body에 넣지 않으며 인증 Principal에서 결정됩니다. 새
생성은 `201`, 같은 Tenant·Key·Body의 재요청은 기존 결과를 `200`으로 반환합니다.

```bash
CSIGHT_IDEMPOTENCY_KEY="$(uuidgen)"
CSIGHT_CASE_RESPONSE="$(
  curl -fsS http://127.0.0.1:8000/api/v1/cases \
    -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" \
    -H "Idempotency-Key: $CSIGHT_IDEMPOTENCY_KEY" \
    -H 'Content-Type: application/json' \
    --data '{
      "order_ref": "ORD-2026-0001",
      "product_ref": "SKU-001",
      "customer_message": "상품 용기가 손상되어 교환을 요청합니다.",
      "requested_action": "EXCHANGE",
      "attributes": {"days_since_purchase": 3}
    }'
)"
CSIGHT_CASE_ID="$(printf '%s' "$CSIGHT_CASE_RESPONSE" | jq -r '.case_id')"
printf '%s\n' "$CSIGHT_CASE_RESPONSE" | jq
unset CSIGHT_CASE_RESPONSE
```

`CSIGHT_IMAGE_PATH`에 Local JPEG, PNG 또는 WebP 경로를 지정해 Evidence를 업로드합니다.

```bash
CSIGHT_IMAGE_PATH='/absolute/path/to/local-test-image.png'
CSIGHT_EVIDENCE_RESPONSE="$(
  curl -fsS "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/evidence" \
    -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" \
    -F 'evidence_type=IMAGE' \
    -F "file=@$CSIGHT_IMAGE_PATH"
)"
CSIGHT_EVIDENCE_ID="$(printf '%s' "$CSIGHT_EVIDENCE_RESPONSE" | jq -r '.evidence_id')"
printf '%s\n' "$CSIGHT_EVIDENCE_RESPONSE" | jq
unset CSIGHT_EVIDENCE_RESPONSE
```

목록·상세와 상태 이력을 조회합니다.

```bash
curl -fsS 'http://127.0.0.1:8000/api/v1/cases?page=1&page_size=20' \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq
curl -fsS "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq
curl -fsS "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/status-history" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq
```

Signed URL은 아래 별도 요청으로 생성합니다. 응답 URL은 Bearer Credential처럼 취급하고
Shell History, 문서, Issue 또는 로그에 복사하지 않습니다.

```bash
curl -fsS -X POST \
  "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/evidence/$CSIGHT_EVIDENCE_ID/access-url" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN"

unset CSIGHT_EVIDENCE_ID CSIGHT_IDEMPOTENCY_KEY
```

전체 HTTP 계약과 역할·오류 매핑은
[`CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md`](CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md)를
참조합니다.

## Sprint 2 Text Analysis 흐름

Reviewer 또는 Admin은 Case와 별도인 Text Analysis Run을 등록할 수 있습니다. 같은
`Idempotency-Key`와 같은 요청은 기존 Run을 `200`으로 재생하고, 새 요청은 `202`와
`Location`을 반환합니다. Dispatcher와 Worker가 비동기로 처리하므로 응답 직후에는
`QUEUED`가 정상입니다.

```bash
CSIGHT_ANALYSIS_KEY="$(uuidgen)"
CSIGHT_ANALYSIS_RESPONSE_FILE="$(mktemp)"
CSIGHT_ANALYSIS_HEADERS="$(
  curl -sS -D - -o "$CSIGHT_ANALYSIS_RESPONSE_FILE" \
    -X POST "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/analysis-runs" \
    -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" \
    -H "Idempotency-Key: $CSIGHT_ANALYSIS_KEY" \
    -H 'Content-Type: application/json' \
    --data '{
      "pipeline": "product_defect_text_extraction",
      "pipeline_version": "1.0.0"
    }'
)"
CSIGHT_ANALYSIS_RUN_ID="$(jq -r '.analysis_run_id' "$CSIGHT_ANALYSIS_RESPONSE_FILE")"
printf '%s\n' "$CSIGHT_ANALYSIS_HEADERS" | sed -n '1p;/^[Ll]ocation:/p'
jq . "$CSIGHT_ANALYSIS_RESPONSE_FILE"

curl -fsS \
  "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/analysis-runs?page=1&page_size=20" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq

curl -fsS \
  "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/analysis-runs/$CSIGHT_ANALYSIS_RUN_ID" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" | jq
```

상세 응답의 `run.status`가 `SUCCEEDED`이면 `extraction_result.result`에 검증된 구조화 결과가
있습니다. 원문 전체 복제본, Raw Prompt, Raw Provider Response, Claim Token과 API Key는
응답이나 DB에 저장되지 않습니다. Case 상세의 `latest_analysis_run`은 최신 Run의 안전한
요약이며 Case 자체 상태는 그대로 유지됩니다.

동일 Key Replay와 충돌을 확인할 수 있습니다.

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/analysis-runs" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" \
  -H "Idempotency-Key: $CSIGHT_ANALYSIS_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"pipeline":"product_defect_text_extraction","pipeline_version":"1.0.0"}'

make smoke-analysis
make test-analysis
```

Mock Timeout·Transient·Permanent·Invalid Schema·Invalid Quote는 기본 테스트에서 네트워크 없이
검증됩니다. 실제 vLLM은 합성 입력만 사용하는 선택적 환경변수를 설정한 뒤에만 실행합니다.
Worker Lost·Hard Timeout은 Late Acknowledgment 재전달로, 검증된 메시지 처리 중 일반 예외와
Soft Timeout은 명시적 재큐잉으로 복구합니다. 활성 Lease 중복 전달은 Lease 만료 시각의
Outbox Wake-up을 남기며, Claim Token이 바뀐 늦은 Worker는 결과를 Commit할 수 없습니다.
최종 허용 Lease까지 만료되면 새 Attempt 없이 `ANALYSIS_MAX_RETRIES_EXCEEDED`로 종결됩니다.

## Sprint 3 Multimodal Analysis 흐름

Image Evidence가 `AVAILABLE`인 Case는 기존 Analysis endpoint에 multimodal pipeline을 요청할
수 있습니다. Run 시작 시 현재 이미지 ID·순서·SHA-256을 Snapshot하며 이후 추가된 Evidence는
기존 Run에 포함되지 않습니다.

```bash
CSIGHT_MULTIMODAL_KEY="$(uuidgen)"
curl -fsS -X POST \
  "http://127.0.0.1:8000/api/v1/cases/$CSIGHT_CASE_ID/analysis-runs" \
  -H "Authorization: Bearer $CSIGHT_ACCESS_TOKEN" \
  -H "Idempotency-Key: $CSIGHT_MULTIMODAL_KEY" \
  -H 'Content-Type: application/json' \
  --data '{
    "pipeline":"product_defect_multimodal_analysis",
    "pipeline_version":"1.0.0"
  }' | jq
```

Text와 Vision Stage/Event는 같은 트랜잭션에 생성되지만 독립 실행된다. 둘 다 성공하면 Run은
`SUCCEEDED`, 하나만 성공하면 결과를 보존한 `PARTIAL_SUCCESS`, 둘 다 실패하면 `FAILED`다.
Vision 결과는 이미지별 `vision_results`에 나타나며 model-native class와 canonical defect,
confidence, `normalized_xyxy` bbox, model/taxonomy/threshold/pre/postprocess version을 포함한다.

기본 `VISION_PROVIDER=mock`은 네트워크 없이 10개 결정론적 시나리오를 지원한다. Remote
Provider는 private `POST /v1/vision/analyze` multipart 계약을 사용하며 Binary, Signed URL,
MinIO credential과 Raw provider JSON을 Queue/DB에 저장하지 않는다. 실제 Vision 검증은
설정된 endpoint와 sample image가 있을 때만 `make test-external-vision`으로 실행한다.

```bash
export RUN_EXTERNAL_GPU_TESTS=1
export LLM_PROVIDER=vllm
export LLM_BASE_URL='http://private-tailscale-host:18000/v1'
export LLM_MODEL_ID='csight-qwen3.8-27b'
export LLM_MODEL_VERSION='Qwen3.8-27B'
export LLM_MODEL_REVISION='63768c10df38c0395e12ef49edac1bd539eaeeea'
# Set LLM_API_KEY from the private runtime secret without printing it.
make test-external-llm
```

Sprint 2.5의 재현 가능한 GPU Node 자산은 [`infra/llm`](infra/llm/README.md), 고정 Artifact와
런타임 기록은
[`qwen38-27b-awq-int4.md`](docs/model-manifests/qwen38-27b-awq-int4.md)에 있습니다. Endpoint는
Tailscale private address에만 bind하고 인증을 필수로 하며, Core readiness에는 포함하지
않습니다. Qwen은 text-only, non-thinking 구조화 추출에만 사용하고 Vision 결함 분석 대체재로
사용하지 않습니다.

```bash
unset CSIGHT_ACCESS_TOKEN CSIGHT_CASE_ID CSIGHT_ANALYSIS_KEY CSIGHT_ANALYSIS_RUN_ID
unset CSIGHT_ANALYSIS_HEADERS
rm -f "$CSIGHT_ANALYSIS_RESPONSE_FILE"
unset CSIGHT_ANALYSIS_RESPONSE_FILE
```

## 설정

설정은 Pydantic Settings가 환경변수 또는 `.env`에서 읽습니다. 키 목록과 로컬 전용
예시값은 [`.env.example`](.env.example)에 있습니다. 실제 비밀번호, API Key, 운영 URL은
저장소에 추가하지 않습니다.

기본 Provider 설정은 외부 GPU를 호출하지 않는 다음 값을 유지합니다.

```dotenv
LLM_PROVIDER=mock
VISION_PROVIDER=mock
```

`/health/ready`는 PostgreSQL 연결, RabbitMQ 연결, MinIO Bucket 존재 여부를 검사합니다.
응답에는 성공/실패 상태만 포함되고 Credential, 전체 Connection String, 내부 IP는
노출하지 않습니다. `/health/live`는 외부 인프라를 조회하지 않습니다.
외부 vLLM 가용성은 Core API Readiness 조건이 아닙니다. 장애는 Analysis Run의 Retry 또는
Failure 상태로 격리됩니다.

Analysis 실행의 핵심 설정은 다음과 같습니다.

| 환경변수 | 기본값 | 설명 |
|---|---:|---|
| `LLM_PROVIDER` | `mock` | `mock` 또는 `vllm` |
| `LLM_MODEL_ID` | `csight-mock-llm` | 실행에 Snapshot되는 Model ID |
| `LLM_CONNECT_TIMEOUT_SECONDS` | `5` | Provider 연결 Timeout |
| `LLM_READ_TIMEOUT_SECONDS` | `120` | Provider 응답 Timeout |
| `ANALYSIS_STAGE_LEASE_SECONDS` | `300` | Worker Fencing Lease |
| `ANALYSIS_OUTBOX_POLL_INTERVAL_SECONDS` | `1` | Dispatcher Poll 주기 |
| `ANALYSIS_OUTBOX_MAX_ATTEMPTS` | `10` | Publish 최대 시도 |

Evidence 업로드와 접근 정책은 다음 설정을 사용합니다.

| 환경변수 | Local 기본값 | 설명 |
|---|---:|---|
| `MAX_UPLOAD_BYTES` | `10485760` | 파일 최대 크기 |
| `ALLOWED_IMAGE_MIME_TYPES` | `image/jpeg,image/png,image/webp` | 허용 MIME |
| `ALLOWED_IMAGE_EXTENSIONS` | `jpg,jpeg,png,webp` | 허용 확장자 |
| `MAX_IMAGE_PIXELS` | `40000000` | `width × height` 상한 |
| `SIGNED_URL_TTL_SECONDS` | `900` | Signed GET URL 수명 |

Evidence 업로드 경로는 이미지의 정확한 `MAX_UPLOAD_BYTES` 검사에 더해 ASGI 경계에서
multipart framing 여유 1 MiB를 포함한 요청 전체 크기를 제한합니다. `Content-Length`가
없어도 제한을 적용합니다. Production의 HTTPS Proxy/Gateway에도 이 값 이상을 무제한
허용하지 않는 요청 본문 상한과 동시 업로드 제한을 설정해야 합니다. `MAX_IMAGE_PIXELS`는
Pillow의 고정 안전 한계 때문에 최대 `178956970`까지 설정할 수 있습니다.

`MINIO_ENDPOINT`는 Core 내부 업로드·삭제 Endpoint이고 `MINIO_PRESIGNED_ENDPOINT`는
클라이언트가 Signed URL로 접근할 Hostname입니다. Production에서는 Bucket을 Private로
유지하고, 신뢰할 수 있는 HTTPS Proxy/Gateway가 서명된 Object GET에 필요한 제한된 경로만
노출해야 합니다. MinIO Console과 Admin API는 공개하지 않습니다.

## 구조

```text
app/
├── interface/      # FastAPI Router, Celery Task, Outbox Dispatcher 진입점
├── application/    # Port만 조율하는 Use Case
├── platform/       # Framework 독립 공통 분석·업무 개념
├── domains/        # 교체 가능한 product_defect_cs 확장점
├── ports/          # LLM, Vision, 저장소, Repository, MQ, Vector 계약
├── adapters/       # SQLAlchemy, Mock/vLLM, Celery Publisher, Readiness 구현
└── bootstrap/      # 설정, 조립, 구조화 로깅
alembic/            # Baseline + Sprint 1 Case/Evidence + Sprint 2 Analysis Migration
infra/              # Core Docker Compose와 공통 App 이미지
tests/              # Unit, Contract, Architecture, Integration, E2E Skeleton
```

`app/platform`과 `app/domains`는 FastAPI, SQLAlchemy, Celery, HTTPX, MinIO 또는
모델 SDK를 import하지 않습니다. 이 규칙과 `app/application → app/adapters` 직접 의존
금지는 AST 기반 Architecture Test가 보호합니다.

LLM과 Vision 결과는 최종 업무 결정이 아닙니다. Sprint 2의 LLM 결과도 구조화된 주장만 반환하며,
향후 최종 결정은 버전 관리된 정책과 Human Review가 소유합니다. 재분석은 새
`analysis_run_id`를 사용하는 append-only 구조를 전제로 하고, 모델·Prompt·Policy·
Threshold·Embedding·Retrieval Index 버전을 기록할 계약을 제공합니다.

## Migration

초기 Baseline은 PostgreSQL `vector` Extension을 생성하고, Sprint 1 Migration은 Tenant,
User, Role, Case, Evidence, 상태 이력과 Case 생성 Idempotency를 추가합니다. Sprint 2
Migration은 기존 Revision을 수정하지 않고 Analysis Run·Stage·Attempt, 구조화 Result,
분석 Idempotency와 Outbox 여섯 테이블을 추가합니다.

```bash
make migrate
docker compose --env-file .env -f infra/compose.core.yml run --rm api uv run alembic current
```

구현 감사와 실제 검증 결과는
[`docs/progress/SPRINT_0_FOUNDATION.md`](docs/progress/SPRINT_0_FOUNDATION.md)와
[`docs/progress/SPRINT_1_CASE_EVIDENCE.md`](docs/progress/SPRINT_1_CASE_EVIDENCE.md),
[`docs/progress/SPRINT_2_ANALYSIS_LLM.md`](docs/progress/SPRINT_2_ANALYSIS_LLM.md)에
기록합니다.

## 협업과 작업 인계

- 현재 구현 상태와 다음 작업은
  [`docs/progress/CURRENT_STATUS.md`](docs/progress/CURRENT_STATUS.md)를 기준으로 확인합니다.
- 브랜치, Pull Request, 병합 규칙은
  [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md)를 따릅니다.
- 기여 절차와 완료 체크리스트는
  [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)에 정리되어 있습니다.
- 모든 작업 세션은 종료 전에 현재 상태 문서의 체크리스트와 append-only 세션 로그를
  갱신합니다.
