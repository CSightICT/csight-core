# AGENTS.md

이 파일은 Codex 및 기타 코딩 에이전트가 CSight 저장소에서 작업할 때 따라야 하는 규칙이다.

## 1. 작업 전 필수 확인

작업을 시작하기 전에 다음 문서를 읽는다.

1. `README.md`
2. 작업과 관련된 `docs/*.md`
3. 관련 `docs/adr/*.md`
4. 기존 테스트와 Migration

문서와 코드가 충돌하면 임의로 결정하지 말고 충돌 지점을 보고한다. 확정된 ADR은 일반 설계 문서보다 우선한다.

## 2. 절대 지켜야 할 아키텍처 규칙

### 2.1 Domain과 Platform Core

- `app/platform`과 순수 Domain 로직은 FastAPI, SQLAlchemy, Celery, HTTPX, vLLM 구현을 직접 import하지 않는다.
- Domain 오류는 `HTTPException`이 아닌 자체 예외로 정의한다.
- ORM Entity를 Domain 함수의 입력으로 직접 전달하지 않는다.
- 외부 기술은 `ports` 인터페이스와 `adapters` 구현을 통해 연결한다.

### 2.2 모델 서버

- LLM·Vision 서버는 업무 DB에 직접 접근하지 않는다.
- 모델 서버는 Case 상태를 변경하지 않는다.
- 모델 서버는 구조화된 분석 결과와 모델 버전만 반환한다.
- LLM과 Vision의 고유 출력은 Adapter에서 공통 Pydantic Schema로 변환한다.

### 2.3 업무 결정

- LLM의 자연어 응답을 최종 환불·교환 결정으로 사용하지 않는다.
- 최종 처리 경로는 분석 결과, 버전 관리된 정책, Human Review를 통해 확정한다.
- `APPROVAL_CANDIDATE`는 최종 승인과 다르다.

### 2.4 분석 이력

- 기존 분석 결과를 덮어쓰지 않는다.
- 재분석은 새로운 `analysis_run`을 생성한다.
- 모든 결과에 다음 버전을 기록한다.
  - CV model
  - LLM model
  - Prompt
  - Policy
  - Threshold
  - Embedding model / Retrieval index

### 2.5 비동기 작업

- 장시간 LLM·Vision 호출을 일반 HTTP 요청 안에서 완료하지 않는다.
- API는 분석 작업을 등록하고 `202 Accepted`와 식별자를 반환한다.
- Celery Task는 얇은 진입점이며 실제 업무 로직은 Application Use Case를 호출한다.
- 동일 메시지가 재전달돼도 중복 실행되지 않도록 `idempotency_key`와 `analysis_run_id`를 사용한다.

## 3. 구현 원칙

- Python 타입 힌트를 필수로 사용한다.
- 외부 입력과 출력은 Pydantic 모델로 검증한다.
- DB 변경에는 반드시 Alembic Migration을 포함한다.
- 공개 API 변경에는 문서, Schema, Contract Test를 함께 수정한다.
- 하드코딩된 상태 문자열 대신 Enum을 사용한다.
- 기업별 정책을 코드에 직접 박아 넣지 않고 버전 관리 가능한 데이터로 저장한다.
- 외부 URL, API Key, 모델명, Threshold는 설정으로 주입한다.
- 로그에는 `case_id`, `analysis_run_id`, `task_id`, `correlation_id`를 포함한다.
- 고객 원문과 이미지 URL을 불필요하게 로그에 남기지 않는다.

## 4. 테스트 규칙

변경 유형별 최소 테스트:

| 변경 | 필수 테스트 |
|---|---|
| Domain 규칙 | Unit Test |
| Repository / DB | Integration Test |
| LLM·Vision Adapter | Contract Test + Mock Test |
| API | Router 또는 E2E Test |
| Migration | Upgrade Test |
| Workflow 상태 전환 | 정상·실패·재시도 Test |
| 정책 변경 | 경계값 및 예외 Test |

테스트에서 실제 외부 GPU 서버를 기본으로 호출하지 않는다. 실제 모델 통합 테스트는 별도 Marker와 환경변수로 실행한다.

## 5. 금지사항

- `main.py` 하나에 Router, DB, 모델 호출, 정책 로직을 모두 작성하지 않는다.
- Domain에서 FastAPI `Request`, `Response`, `HTTPException`을 사용하지 않는다.
- Vision class id 숫자를 비즈니스 로직에서 직접 비교하지 않는다.
- Base64 이미지를 RabbitMQ 메시지에 넣지 않는다.
- 모델 실패 시 고객 텍스트만으로 자동 승인하지 않는다.
- 근거 없이 새로운 인프라(Kafka, Kubernetes, Redis 등)를 추가하지 않는다.
- 테스트를 통과시키기 위해 실제 로직을 빈 Mock으로 대체하지 않는다.
- 검증되지 않은 수치나 성능을 문서에 사실처럼 기록하지 않는다.

## 6. 완료 정의

작업은 다음 조건을 모두 충족해야 완료로 본다.

- 요구사항과 인수조건 충족
- 관련 테스트 통과
- Ruff 및 타입 검사 통과
- Migration 포함 및 롤백 영향 검토
- API·Event Schema 업데이트
- 로그와 오류 처리 추가
- 문서 또는 ADR 업데이트
- 보안·개인정보 영향 검토
- 기존 기능 회귀 없음

## 7. 권장 명령 예시

실제 프로젝트 구성 후 아래 명령을 표준화한다.

```bash
ruff check .
ruff format --check .
pytest -q
alembic upgrade head
docker compose -f infra/compose.core.yml up -d
```

명령이 실제 저장소와 다르면 `README.md`와 이 파일을 함께 수정한다.

## 8. 작업 상태 및 세션 인계

- 모든 작업은 시작할 때 루트의 `docs/progress/CURRENT_STATUS.md`와 관련 Sprint 작업
  기록을 확인한다.
- 모든 작업은 종료하기 전에 `CURRENT_STATUS.md`의 현재 상태, 실제 검증 결과,
  미해결 사항, 다음 실행 항목을 갱신한다.
- 검증 상태는 `PASS`, `FAIL`, `NOT_RUN`, `SKIPPED`, `BLOCKED`만 사용하며, 실행하지
  않은 검사를 `PASS`로 기록하지 않는다.
- 외부 서비스와 실행 중 프로세스 상태에는 관측 시각을 적는다. 과거 관측값을 현재도
  유효한 영구 상태처럼 표현하지 않는다.
- 세션 로그는 append-only로 유지한다. 과거 기록을 정정할 때는 원문을 삭제하지 않고
  새 정정 기록을 추가한다.
- 체크리스트와 로그에는 Secret, 고객 원문, Presigned URL, 전체 Connection String을
  기록하지 않는다.
- 새로운 아키텍처 결정은 Progress 문서에만 남기지 않고 관련 설계 문서 또는 ADR에도
  반영한다.
