# Sprint 1 Closeout 감사 및 로컬 기준점

- 감사일: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-1-case-evidence`
- 감사 기준 Base: `a78478a` (`chore/github-governance`)
- 범위: Sprint 1 Case & Evidence Vertical Slice의 Commit 전 전체 Diff
- 결론: P0/P1 미해결 0건, 로컬 기준점 Commit 가능, Push 금지

## 1. 감사 범위와 Commit 경계

다음 범위를 실제 코드·Migration·설정·테스트·문서 기준으로 독립 재검토했다.

- Local/Test Identity Seed, Argon2id, HS256 JWT와 현재 계정·역할 재조회
- Principal 기반 Tenant Scope와 역할 권한
- Case 생성·목록·상세·상태 이력 및 PostgreSQL Idempotency
- JPEG·PNG·WebP 검증, 요청 상한, Private MinIO와 실패 보상
- Signed URL, 오류 Envelope, Cache·로그·Secret 안전성
- Sprint 0 Baseline을 보존한 Sprint 1 Migration과 Schema Drift
- Architecture Boundary, Docker Compose, Seed와 실제 HTTP Vertical Slice

Commit 후보는 Sprint 1 코드, 테스트, Migration, ADR·설계·진행 문서만 포함한다. 다음은
명시적으로 제외한다.

- `.env`, 실제 Secret, Token, Signed URL, Connection String
- `.pytest_cache`, `.ruff_cache`, `__pycache__`, 테스트 이미지·DB Dump·로그
- 별도 사용자 작업물 `kaputt_best_vision_architecture.md`

`alembic/versions/20260825_0001_pgvector_baseline.py`의 Diff는 비어 있으며 Sprint 0 Baseline을
수정하지 않았다. `kaputt_best_vision_architecture.md`는 Sprint 2 Vision 연구 성격의 미추적
문서이고 Closeout 범위가 아니므로 수정·삭제·Stage하지 않았다.

## 2. 발견 및 처리 결과

| 등급 | 발견 | 수정 | 미해결 |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 3 | 3 | 0 |
| P2 | 4 | 4 | 0 |
| P3 | 7 | 0 | 7 |

### P1 — 모두 수정

1. `QUALITY_VIEWER`의 타 Tenant Evidence 업로드에서 Role `403`이 Tenant `404`보다 먼저
   반환됐다. Tenant-scoped Parent Case를 먼저 확인하고, In-tenant Case에만 쓰기 권한을
   검사하도록 순서를 바로잡았다.
2. `DATABASE_ECHO=true`에서 SQLAlchemy Bind Parameter로 고객 원문이 로그에 출력될 수
   있었다. 모든 Engine을 `hide_parameters=True`로 만들고 실제 로그에 Marker가 없는지
   회귀 테스트했다.
3. DB가 `AVAILABLE`이지만 Object가 없는 Evidence도 Signed URL을 성공 반환했다. URL 생성
   전에 내부 MinIO HEAD를 강제하고 누락은 `500 EVIDENCE_UPLOAD_FAILED`, HEAD 장애는
   `503 STORAGE_UNAVAILABLE`로 분리했다.

### P2 — 모두 보강

1. File Inspector에 명시적 빈 Allowlist를 주입하면 기본 JPEG·PNG·WebP로 되돌아가던
   Adapter 불변조건을 Fail-closed로 수정했다.
2. 타 Tenant가 Access URL Endpoint를 직접 호출하는 실제 HTTP 격리 테스트를 추가했다.
3. 지원 형식의 Animated 이미지와 Pillow Hard Decompression Bomb 오류를 직접 검증하는
   테스트를 추가했다.
4. 기존 Offline SQL·공유 Head Catalog 확인 외에 격리 임시 DB에서 빈 DB→Head,
   Sprint 0→Sprint 1, Head→Sprint 0→Head를 실제 실행하고 Cross-tenant 복합 FK 거부를
   확인했다. 임시 DB는 검증 종료 후 모두 삭제했다.

### P3 — 후속 범위

1. 강제 종료·보상 중첩 실패 뒤 `PENDING` Row와 고아 Object Reconciliation/정리 작업
2. Evidence 업로드 Idempotency와 Idempotency 만료 Cleanup·Key 재사용
3. EXIF 제거, 재인코딩, 개인정보 마스킹, 파생본과 악성코드 검사
4. 고객 원문·원본·Audit·Idempotency의 Retention과 삭제 정책
5. Refresh Token·Revocation·OIDC/SSO·다중 Tenant 전환·PostgreSQL RLS
6. Production MinIO 최소권한 서비스 계정, 제한된 Presign Gateway, Secret Rotation과
   Edge 요청·동시성 제한
7. Privileged CI Migration 수명주기 자동화와 추가 Thread 경쟁·Transaction Fault 주입;
   실제 LLM·Vision·Analysis Run은 별도 Sprint 2 범위

P3는 이번 Vertical Slice의 완료 조건을 위반하지 않으며, 새 기능 구현 없이 다음 작업으로
이관한다.

## 3. Closeout에서 수정한 파일

| 파일 | 목적 |
|---|---|
| `app/application/evidence.py` | 타 Tenant 404 우선순위와 URL 전 Object HEAD 강제 |
| `app/adapters/persistence/engine.py` | SQL Bind Parameter 로그 비노출 |
| `app/adapters/file_inspection/pillow.py` | 명시적 빈 Allowlist Fail-closed |
| `tests/unit/test_evidence_use_cases.py` | 역할·Tenant 순서와 누락 Object URL 회귀 |
| `tests/unit/test_persistence_foundation.py` | SQL Echo 민감값 비노출 회귀 |
| `tests/unit/test_file_inspection.py` | 빈 Allowlist, Animated, Hard Bomb 회귀 |
| `tests/integration/test_sprint1_http_e2e.py` | 실제 Cross-tenant 업로드·URL과 누락 Object 검증 |
| `CSight_project_docs/docs/05_API_AND_EVENT_CONTRACTS.md` | Object HEAD 오류 계약 동기화 |
| `CSight_project_docs/docs/08_SECURITY_AND_OPERATIONS.md` | 로그·Object 누락 운영 Guardrail |
| `docs/progress/SPRINT_1_CASE_EVIDENCE.md` | Closeout 최종 상태와 검증 수치 연결 |
| `docs/progress/CURRENT_STATUS.md` | 다음 세션 인계, 체크리스트와 Session Log |
| `docs/progress/SPRINT_1_CLOSEOUT.md` | 본 독립 감사 원장 |

## 4. 보안 검토

- Tenant: 모든 Repository 연산은 명시적 `tenant_id`를 요구하고 SQL에도 Scope가 있다.
  공개 입력의 Tenant를 신뢰하지 않으며 다른 Tenant ID는 역할과 무관하게 `404`다.
- Idempotency: `(tenant_id, operation, key)` Unique와 PostgreSQL
  `ON CONFLICT DO NOTHING`을 사용한다. Claim·Case·최초 History는 한 UoW Transaction이다.
- JWT: HS256 Allowlist, Issuer·Audience·필수 Claim·만료를 검증하고 매 요청마다 현재 활성
  계정과 DB Role을 다시 조회한다.
- 파일: 전체 Byte 상한과 SHA-256, 실제 Decode, 형식·확장자·MIME, 단일 Frame, Pixel 및
  Pillow Hard Limit을 확인한다. 사용자 파일명은 Object Key에 사용하지 않는다.
- MinIO: Bucket은 Private이고 PUT 후 HEAD의 크기·MIME·SHA-256을 확인한다. Signed URL도
  Tenant 조회와 별도 HEAD를 통과한 `AVAILABLE` Object에만 발급한다.
- 로그·Secret: SQL Bind 값, Password, JWT, Credential, Signed URL, Binary와 전체
  Connection String을 기록하지 않는다. `.env`는 Ignore 상태이며 Commit 후보에 없다.

## 5. 실제 검증 결과

| 검사 | 결과 |
|---|---|
| Ruff | PASS — 전체 Lint |
| Ruff Format | PASS — Sprint 1 Commit 후보 전체; 별도 미추적 Kaputt 문서는 제외 |
| Pyright strict | PASS — 0 errors, 0 warnings, 0 informations |
| Unit | PASS — 168 |
| Contract | PASS — 14 |
| Architecture | PASS — 4 |
| HTTP API | PASS — 15 |
| 기본 E2E | PASS — 3 |
| `make test-all` | PASS — Fast 189, Integration 18 |
| PostgreSQL 대상 | PASS — 10 |
| MinIO·보상 대상 | PASS — 3 |
| 실제 HTTP Integration E2E | PASS — 1 |
| 빈 DB Migration | PASS — `20260826_0002` Head, Drift 없음 |
| Sprint 0→Sprint 1 | PASS — Baseline `20260825_0001`에서 Head |
| Migration 왕복·FK | PASS — Head→Baseline→Head, Cross-tenant Evidence 거부 |
| Compose Build·실행 | PASS — API, Worker, PostgreSQL, RabbitMQ, MinIO Healthy |
| Seed 2회 | PASS — Tenant 1, User 3, Role 3 유지 |
| Live HTTP | PASS — Login, Case 201/Replay 200, Evidence, Signed GET, Object HEAD |
| Live Tenant 격리 | PASS — A→B와 B→A `404`, 타 Tenant URL `404` |
| 누락 Object | PASS — `AVAILABLE` Row여도 URL `500`, 성공 응답 없음 |
| 검증 데이터 정리 | PASS — 업무 Row 0, MinIO Object 0 |

처음 시도한 Live 스크립트는 설치되지 않은 직접 `httpx` Import 단계에서 상태 변경 없이
중단됐고 PASS로 계산하지 않았다. 동일 시나리오는 표준 라이브러리 HTTP Client로 다시
실행해 통과했다. Token·Password·Signed URL·Connection String은 결과에 출력하지 않았다.

저장소 루트의 `ruff format --check .`는 범위 밖 미추적 Kaputt 문서의 Python 코드 블록
2곳을 보고했다. 사용자 파일을 변경해 검사를 통과시키지 않았으며, Commit 후보를 명시적으로
제한한 동일 Formatter 검사는 통과했다.

## 6. Migration 상태

```text
20260825_0001  Sprint 0 pgvector baseline (변경 없음)
        ↓
20260826_0002  Sprint 1 identity, Case, Evidence, idempotency (head)
```

빈 임시 DB와 Baseline 임시 DB를 별도로 만들었다. Upgrade·Downgrade·Drift·복합 FK를 실제
PostgreSQL에서 확인한 뒤 UUID 기반 임시 DB 2개를 정확히 삭제했다. Sprint 1 Downgrade는
8개 업무 테이블과 데이터를 삭제하므로 운영 데이터가 있는 환경에서는 자동 실행하지 않는다.

## 7. Sprint 2 시작 조건과 알려진 제한

기술 기준은 `READY`다. Sprint 2는 다음 조건을 유지해야 한다.

- 본 Closeout 로컬 Commit을 재현 가능한 Base로 사용한다.
- Case/Evidence 접수와 분석 시작 API를 분리한다.
- Analysis Run은 Append-only이며 모델·Prompt·Policy·Threshold·Embedding·Retrieval Index
  버전을 기록한다.
- Celery Task는 얇은 Application Use Case 진입점으로 유지한다.
- 기본 테스트에서 외부 GPU·실제 LLM·Vision을 호출하지 않는다.
- 위 P3 운영·보안 항목은 실제 데이터·Production 반입 전에 우선순위를 결정한다.

이번 작업에서는 Sprint 2 구현, Git Push와 PR 생성을 수행하지 않는다. Commit SHA는
자기참조를 피하기 위해 문서에 고정하지 않고 Commit 후 `git log -1 --oneline` 결과로
보고한다.
