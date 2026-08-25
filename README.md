# CSight

> 이미지·텍스트 기반 상품 불량 CS 의사결정 지원 플랫폼

이 저장소는 CSight의 **Sprint 1 Case & Evidence Vertical Slice**입니다. Python 3.12,
FastAPI, SQLAlchemy 2/Alembic, Celery/RabbitMQ, PostgreSQL/pgvector, MinIO를 사용하며,
API와 Worker는 같은 이미지에서 서로 다른 프로세스로 실행됩니다.

Sprint 1에는 로컬·PoC JWT 로그인, Principal 기반 Tenant 격리, Case 생성·목록·상세·상태
이력, 이미지 Evidence 검증·Private MinIO 저장·Signed URL이 포함됩니다. 실제 정책 판정,
RAG, Human Review와 외부 LLM·Vision 호출은 없으며 Case/Evidence 접수 후 분석을 자동
시작하지 않습니다. Sprint 0의 AI 경계와 결정적 Mock Adapter는 그대로 유지합니다.
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
Worker를 시작한 뒤 Health Check를 기다립니다. 모든 외부 포트는 `127.0.0.1`에만
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
| Ruff Lint | `make lint` |
| Ruff Format 검사 | `make format-check` |
| Pyright Type Check | `make typecheck` |
| CI-safe 테스트 | `make test` |
| Core 통합 테스트 | `make test-integration` |
| 전체 로컬 테스트 | `make test-all` |

`make test`는 Docker 인프라와 GPU를 요구하지 않습니다. `make test-integration`과
`make test-all`은 먼저 `make up`과 `make migrate`를 실행한 상태에서 사용합니다.
외부 GPU 테스트는 별도 `external_gpu` Marker로 격리되며 기본 명령에서 실행되지 않습니다.

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

unset CSIGHT_ACCESS_TOKEN CSIGHT_CASE_ID CSIGHT_EVIDENCE_ID CSIGHT_IDEMPOTENCY_KEY
```

전체 HTTP 계약과 역할·오류 매핑은
[`CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md`](CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md)를
참조합니다.

## 설정

설정은 Pydantic Settings가 환경변수 또는 `.env`에서 읽습니다. 키 목록과 로컬 전용
예시값은 [`.env.example`](.env.example)에 있습니다. 실제 비밀번호, API Key, 운영 URL은
저장소에 추가하지 않습니다.

Sprint 0의 Provider 설정은 반드시 다음 기본값을 유지합니다.

```dotenv
LLM_PROVIDER=mock
VISION_PROVIDER=mock
```

`/health/ready`는 PostgreSQL 연결, RabbitMQ 연결, MinIO Bucket 존재 여부를 검사합니다.
응답에는 성공/실패 상태만 포함되고 Credential, 전체 Connection String, 내부 IP는
노출하지 않습니다. `/health/live`는 외부 인프라를 조회하지 않습니다.

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
├── interface/      # FastAPI Router, Celery Task, Event 진입점
├── application/    # Port만 조율하는 Use Case
├── platform/       # Framework 독립 공통 분석·업무 개념
├── domains/        # 교체 가능한 product_defect_cs 확장점
├── ports/          # LLM, Vision, 저장소, Repository, MQ, Vector 계약
├── adapters/       # SQLAlchemy, Mock AI, Readiness 구현
└── bootstrap/      # 설정, 조립, 구조화 로깅
alembic/            # pgvector Baseline + Sprint 1 Identity/Case/Evidence Migration
infra/              # Core Docker Compose와 공통 App 이미지
tests/              # Unit, Contract, Architecture, Integration, E2E Skeleton
```

`app/platform`과 `app/domains`는 FastAPI, SQLAlchemy, Celery, HTTPX, MinIO 또는
모델 SDK를 import하지 않습니다. 이 규칙과 `app/application → app/adapters` 직접 의존
금지는 AST 기반 Architecture Test가 보호합니다.

LLM과 Vision 결과는 최종 업무 결정이 아닙니다. Mock E2E 결과도 분석 관찰값만 반환하며,
향후 최종 결정은 버전 관리된 정책과 Human Review가 소유합니다. 재분석은 새
`analysis_run_id`를 사용하는 append-only 구조를 전제로 하고, 모델·Prompt·Policy·
Threshold·Embedding·Retrieval Index 버전을 기록할 계약을 제공합니다.

## Migration

초기 Baseline은 PostgreSQL `vector` Extension을 생성하고, Sprint 1 Migration은 그
Baseline을 수정하지 않은 채 Tenant, User, Role, Case, Evidence, 상태 이력과 Case 생성
Idempotency 테이블을 추가합니다.

```bash
make migrate
docker compose --env-file .env -f infra/compose.core.yml run --rm api uv run alembic current
```

구현 감사와 실제 검증 결과는
[`docs/progress/SPRINT_0_FOUNDATION.md`](docs/progress/SPRINT_0_FOUNDATION.md)와
[`docs/progress/SPRINT_1_CASE_EVIDENCE.md`](docs/progress/SPRINT_1_CASE_EVIDENCE.md)에
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
