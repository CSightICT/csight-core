# Sprint 0 Foundation 작업 기록

- 작업 시작일: 2026-08-25
- 최종 검증일: 2026-08-26 (Asia/Seoul)
- 범위: 실행 가능한 Sprint 0 기반만 구현

## 1. 작업 전 저장소 상태

- 현재 작업 디렉터리는 Git 저장소가 아니었다. `.git`이 없어서 Branch, Commit,
  기존 변경사항을 비교할 수 없었다.
- 루트에는 `.DS_Store`와 기존 `CSight_project_docs/` 문서·SVG 자산만 있었다.
- Python 프로젝트 설정, 애플리케이션 코드, Docker/Compose, Migration, 테스트,
  CI 설정은 없었다.
- 기존 문서와 SVG는 삭제하거나 이동하지 않았다. 새 애플리케이션은 사용자가 지정한
  현재 디렉터리 자체를 프로젝트 루트로 사용한다.

## 2. 확인한 문서

다음 문서를 요청된 우선순위에 따라 모두 확인했다.

1. `CSight_project_docs/AGENTS.md`
2. `CSight_project_docs/README.md`
3. `CSight_project_docs/PROJECT_BLUEPRINT.md`
4. `CSight_project_docs/docs/01_PROJECT_CHARTER.md`
5. `CSight_project_docs/docs/02_PRODUCT_REQUIREMENTS.md`
6. `CSight_project_docs/docs/03_ARCHITECTURE.md`
7. `CSight_project_docs/docs/04_DOMAIN_MODEL_AND_WORKFLOW.md`
8. `CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md`
9. `CSight_project_docs/docs/06_DATA_AND_ML_PLAN.md`
10. `CSight_project_docs/docs/07_DATABASE_DESIGN.md`
11. `CSight_project_docs/docs/08_SECURITY_AND_OPERATIONS.md`
12. `CSight_project_docs/docs/09_TESTING_AND_EVALUATION.md`
13. `CSight_project_docs/docs/10_ROADMAP_AND_BACKLOG.md`
14. `CSight_project_docs/docs/adr/0001`부터 `0005`까지의 Accepted ADR 전체

## 3. 발견한 모순·미확정 사항

치명적인 구현 차단 사항은 없었다. 다음 항목은 Sprint 0 범위에 맞게 해석했다.

- 설계 문서는 문서 폴더 자체를 예시 저장소 루트로 표현하지만 실제 작업 시작 시 문서가
  `CSight_project_docs/` 아래에 있었다. 기존 파일을 이동하지 않고, 코드·인프라·실행 문서는
  현재 작업 루트에 생성했다.
- Roadmap은 본격적인 Celery 분석 흐름을 Sprint 2에 배치하지만 이번 Sprint 0 요청은
  RabbitMQ 연결과 Mock 분석 Task Skeleton을 명시한다. 따라서 저장·상태전환·Idempotency
  업무 로직 없이 얇은 Worker 진입점만 구현했다.
- DB 설계 문서에는 전체 업무 테이블 후보가 있으나 Sprint 0 요청은 과도한 선행 Schema를
  금지한다. Baseline은 Alembic 버전 테이블과 `vector` Extension만 준비한다.
- 첫 상품군, 결함 Taxonomy 최종안, 정책 표현, 개인정보 보관기간, 실제 Vision 출력 규격은
  여전히 미확정이다. Mock 공통 계약은 이 결정들을 고정하지 않는다.
- 인증·Tenant 업무 Scope, 실제 Provider URL, 운영 Secret, 보관·삭제 정책은 후속 Sprint
  결정으로 남겼다.

## 4. 이번 Sprint의 구현 방식

### Python과 품질 도구

- Python `>=3.12,<3.13`, `uv`, 고정된 직접 의존성, 재현 가능한 `uv.lock`
- Ruff, Ruff Format, Pyright strict, pytest와 요청된 Marker
- FastAPI, Pydantic v2/Pydantic Settings, 동기 SQLAlchemy 2, Alembic
- Celery/Kombu + RabbitMQ, MinIO Python SDK, structlog JSON Logging

### 계층과 경계

- `interface → application → ports/platform` 의존 방향을 유지한다.
- Adapter 조립은 `bootstrap`에서만 수행한다.
- `app/platform`과 `app/domains`의 외부 Framework/SDK import 금지 및
  `app/application`의 concrete Adapter import 금지를 AST 테스트로 검사한다.
- LLM·Vision Mock은 구조화된 분석만 반환하고 정책·최종 결정을 만들지 않는다.
- `AnalysisVersionReferences`는 LLM, Vision, Prompt, Policy, Threshold, Embedding,
  Retrieval Index 버전을 기록할 수 있다.

### API와 Readiness

- `GET /health/live`: 외부 의존성을 호출하지 않는다.
- `GET /health/ready`: PostgreSQL `SELECT 1`, RabbitMQ 연결, MinIO Bucket 존재 여부를
  검사하고 실패 시 민감한 상세 없이 `503`을 반환한다.
- `GET /api/v1/system/info`: 서비스명, 앱 버전, 환경, API Schema 버전만 노출한다.
- 공통 오류 Envelope와 HTTP 변환은 Interface 계층에 둔다.

### DB와 Worker

- SQLAlchemy Engine/Session, Typed Declarative Base, Naming Convention을 구성했다.
- Baseline Migration은 `CREATE EXTENSION IF NOT EXISTS vector`만 수행한다.
- API와 Worker는 동일한 non-root Python 3.12 이미지를 사용한다.
- Worker는 `default`, `analysis` Queue를 소비하고, Timeout/운영 실패에 제한된 Retry를
  적용한다.
- Task는 Application Use Case만 호출한다. Celery 성공 로그에 고객 텍스트나 이미지
  참조가 포함되지 않도록 비민감 완료 메타데이터만 반환한다.

### Docker Compose와 CI

- pgvector/PostgreSQL, RabbitMQ Management, MinIO, Bucket init, API, Worker를 구성했다.
- Named Volume, 모든 장기 서비스 Health Check, 의존성 준비 순서, `127.0.0.1` 전용
  포트 바인딩을 적용했다.
- App 및 선택한 Upstream 이미지는 Docker Desktop aarch64에서 네이티브 실행됨을
  확인했다. `linux/amd64` 강제 설정은 없다.
- GitHub Actions는 lockfile 설치, Ruff, Format Check, Pyright, CI-safe pytest를 수행한다.
  원격 GitHub Actions Run은 Git 저장소가 없으므로 실행하지 않았고, 동일 로컬 명령만
  검증했다.

## 5. 실행 방법

```bash
cp .env.example .env
uv sync --frozen --group dev
make up
make migrate
```

확인:

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsS http://127.0.0.1:8000/api/v1/system/info
```

품질 검사:

```bash
make lint
make format-check
make typecheck
make test
make test-integration
make test-all
```

종료:

```bash
make down
```

## 6. 실제 검증 결과

| 검사 | 실행 결과 |
|---|---|
| `uv sync --frozen --group dev` | 통과, Python 3.12 환경과 lockfile 설치 완료 |
| Compose Config | 통과 |
| `make up` | 통과, App 이미지 Build 및 모든 장기 서비스 Healthy |
| App 이미지 | `linux/arm64`, non-root `csight` 사용자 확인 |
| PostgreSQL | Healthy, `SELECT 1` 통과 |
| Alembic | `20260825_0001` Head 적용 통과 |
| pgvector | Extension `0.8.6` 확인 |
| RabbitMQ / Worker | Healthy, AMQP 연결 및 `analysis` Queue Mock Task 완료 |
| MinIO | Healthy, `csight-evidence` Bucket 생성 및 Private 확인 |
| `/health/live` | `200`, 예상 계약 일치 |
| `/health/ready` 정상 | `200`, PostgreSQL/RabbitMQ/MinIO 모두 `ok` |
| `/health/ready` 장애 | RabbitMQ 중지 시 `503` 및 `rabbitmq=unavailable`, 복구 후 `200` |
| `/api/v1/system/info` | `200`, 비민감 필드만 반환 |
| Ruff | 통과 |
| Ruff Format Check | 통과 |
| Pyright strict | `0 errors, 0 warnings` |
| 기본 pytest | `37 passed`, Integration 4건 deselected, 외부 GPU 호출 없음 |
| Core Integration | `4 passed` (PostgreSQL, Alembic/pgvector, RabbitMQ, MinIO) |
| Architecture Test | `2 passed` |
| Contract Test | `14 passed` |
| E2E Skeleton | `3 passed` |
| `make test-all` | 기본 37건 + Core Integration 4건 모두 통과 |

최종 확인 시 Core Stack은 실행 중이다. 필요하면 `make down`으로 Named Volume을 보존한
채 종료할 수 있다.

## 7. 후속 Sprint로 넘긴 항목

- 실제 Case/Evidence CRUD, 파일 검증, MinIO 업로드
- Tenant Scope와 인증/JWT
- Analysis Run/결과의 append-only DB 영속화 및 Idempotency
- 실제 vLLM/Vision HTTP Adapter, Timeout/Partial Failure 영속화
- Domain Taxonomy, Alignment, Policy Evaluator, Routing
- Human Review, Audit, Report
- pgvector Retrieval/RAG
- 개인정보 보관·삭제 정책과 운영 Secret 관리
- 원격 Git 저장소 생성 후 GitHub Actions 실제 Run 확인
