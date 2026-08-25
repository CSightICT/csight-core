# CSight

> 이미지·텍스트 기반 상품 불량 CS 의사결정 지원 플랫폼

이 저장소는 CSight의 실행 가능한 **Sprint 0 Foundation**입니다. Python 3.12,
FastAPI, SQLAlchemy 2/Alembic, Celery/RabbitMQ, PostgreSQL/pgvector, MinIO를 사용하며,
API와 Worker는 같은 이미지에서 서로 다른 프로세스로 실행됩니다.

Sprint 0에는 실제 Case CRUD, Evidence 업로드, 정책 판정, RAG, 인증, Human Review,
외부 LLM·Vision 호출이 없습니다. AI 경계는 공통 Pydantic 계약과 네트워크를 사용하지 않는
결정적 Mock Adapter로만 검증합니다. 설계 원문과 SVG 자산은
[`CSight_project_docs/`](CSight_project_docs/)에 그대로 보존되어 있습니다.

## 빠른 시작

필수 도구:

- Docker Desktop과 Docker Compose
- [`uv`](https://docs.astral.sh/uv/) (호스트 품질 검사와 테스트용)

프로젝트 루트에서 다음 명령을 실행합니다.

```bash
cp .env.example .env
uv sync --frozen --group dev
make up
make migrate
```

`make up`은 이미지를 빌드하고 PostgreSQL, RabbitMQ, MinIO, Bucket 초기화, API,
Worker를 시작한 뒤 Health Check를 기다립니다. 모든 외부 포트는 `127.0.0.1`에만
바인딩됩니다.

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
| Ruff Lint | `make lint` |
| Ruff Format 검사 | `make format-check` |
| Pyright Type Check | `make typecheck` |
| CI-safe 테스트 | `make test` |
| Core 통합 테스트 | `make test-integration` |
| 전체 로컬 테스트 | `make test-all` |

`make test`는 Docker 인프라와 GPU를 요구하지 않습니다. `make test-integration`과
`make test-all`은 먼저 `make up`과 `make migrate`를 실행한 상태에서 사용합니다.
외부 GPU 테스트는 별도 `external_gpu` Marker로 격리되며 기본 명령에서 실행되지 않습니다.

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
alembic/            # pgvector Extension만 준비하는 Baseline Migration
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

초기 Baseline은 PostgreSQL `vector` Extension과 Alembic 버전 테이블만 생성합니다.
Sprint 1 이전에 업무 테이블을 선행 생성하지 않습니다.

```bash
make migrate
docker compose --env-file .env -f infra/compose.core.yml run --rm api uv run alembic current
```

구현 감사와 실제 검증 결과는
[`docs/progress/SPRINT_0_FOUNDATION.md`](docs/progress/SPRINT_0_FOUNDATION.md)에 기록합니다.

## 협업과 작업 인계

- 현재 구현 상태와 다음 작업은
  [`docs/progress/CURRENT_STATUS.md`](docs/progress/CURRENT_STATUS.md)를 기준으로 확인합니다.
- 브랜치, Pull Request, 병합 규칙은
  [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md)를 따릅니다.
- 기여 절차와 완료 체크리스트는
  [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)에 정리되어 있습니다.
- 모든 작업 세션은 종료 전에 현재 상태 문서의 체크리스트와 append-only 세션 로그를
  갱신합니다.
