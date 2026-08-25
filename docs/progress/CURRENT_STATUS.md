# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 구현 증거는 `SPRINT_0_FOUNDATION.md`와
`SPRINT_1_CASE_EVIDENCE.md`, 독립 감사 증거는 `SPRINT_1_CLOSEOUT.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 1 — Case & Evidence Vertical Slice Closeout |
| 진행 중 작업 | 독립 감사·전체 검증 완료, 이 문서를 포함한 로컬 기준점 Commit 생성; Push 미수행 |
| 마지막 갱신일 | 2026-08-26, Asia/Seoul |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | `CSightICT/csight-core` — Private, Sprint 1 변경은 Push하지 않음 |
| 로컬 Git | `feature/sprint-1-case-evidence`, Closeout 로컬 Commit이 Branch Tip, `chore/github-governance` 기반, PR #2 Open |
| 마지막 런타임 관측 | 2026-08-26, Closeout 이미지 재빌드 후 Core 장기 서비스 5개 Healthy |

## 1. 다음 세션 시작 체크리스트

- [ ] `CSight_project_docs/AGENTS.md`, 관련 설계 문서, Accepted ADR을 읽는다.
- [ ] 이 문서의 진행 중 작업, 미해결 사항, 다음 작업을 확인한다.
- [ ] `pwd`, `git status --short --branch`, `git remote -v`로 실제 저장소 상태를 확인한다.
- [ ] 필요하면 `docker compose --env-file .env -f infra/compose.core.yml ps`로 런타임을
  다시 확인한다.
- [ ] 변경 전 관련 테스트, Migration, API/Event 계약을 확인한다.
- [ ] 이번 세션의 범위와 하지 않을 일을 명시한다.
- [ ] 아래의 첫 번째 미완료 실행 항목부터 진행한다.

## 2. 단계별 상태

| 단계 | 상태 | 근거 또는 다음 조건 |
|---|---|---|
| Sprint 0 Foundation 구현 | PASS | 상세 기록과 2026-08-26 검증 결과 존재 |
| Sprint 1 Case & Evidence 구현 | PASS | 인증→Case→Evidence→Signed URL E2E와 전체 회귀 통과 |
| Sprint 1 독립 Closeout | PASS | P0/P1 미해결 0, 격리 Migration·Live Tenant·Object HEAD 포함 |
| Sprint 1 Migration·Seed | PASS | Head `20260826_0002`, Drift 없음, Seed 2회 반복 성공 |
| Sprint 1 Tenant·파일 보안 | PASS | Principal Scope, Role, Private MinIO, 실제 저장 메타데이터 검증, 요청·이미지 상한 적용 |
| GitHub 협업 문서·템플릿 | PASS | 브랜치 규칙, PR·Issue 템플릿, CODEOWNERS 작성 |
| 초기 Git 안전성 감사 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, 방어 Ignore 보강 |
| 로컬 Git 초기화 | PASS | `main` 초기 커밋 `6fc20d3`, 로컬 `develop` 준비 |
| GitHub 조직·저장소 | PASS | `CSightICT`와 Private `CSightICT/csight-core` 생성 확인 |
| GitHub 플러그인 조직 접근 | PASS | ChatGPT Codex Connector를 `CSightICT/csight-core`에만 설치하고 조회 확인 |
| 원격 브랜치·초기 CI | PASS | `main`·`develop`·작업 브랜치 Push, 세 초기 Actions Run 성공 |
| GitHub 거버넌스 PR | PASS | `chore/github-governance` → `develop` PR #2 Open, 최신 CI 성공 |
| `main`·`develop` 보호 규칙 | BLOCKED | Private 저장소의 현재 플랜에서 API HTTP 403; Issue #1로 추적 |

## 3. Sprint 0 완료 체크리스트

- [x] Python 3.12, `uv.lock`, Ruff, Pyright strict, pytest 기반
- [x] FastAPI health/readiness/system-info API
- [x] PostgreSQL/pgvector, RabbitMQ, MinIO Core Compose
- [x] Alembic vector baseline
- [x] LLM·Vision Port와 deterministic Mock Adapter
- [x] 분석 전체 버전 참조 계약
- [x] 얇은 Celery Application Use Case 진입점
- [x] 구조화 로그와 민감정보 Redaction
- [x] Architecture, Contract, E2E, Integration 테스트
- [x] ARM64 Docker 및 CI-safe GitHub Actions Workflow
- [x] GitHub Actions 원격 실행

## 4. Sprint 1 완료 체크리스트

- [x] 작업 전 Sprint 0 정적 검사·테스트·Compose·Health·Migration 회귀 확인
- [x] 기술 독립 Case/Evidence Domain, Enum, Port와 Application Use Case 구현
- [x] 기존 Baseline을 보존한 `20260826_0002` Migration과 8개 테이블 구현
- [x] Local/Test 전용 Idempotent Seed, Argon2id 로그인, HS256 JWT와 현재 Role 재조회
- [x] Principal 기반 Tenant Scope와 ADMIN·REVIEWER·QUALITY_VIEWER 권한 적용
- [x] Case 생성·목록·상세·상태 이력과 Tenant 단위 생성 Idempotency 구현
- [x] JPEG·PNG·WebP 실제 Decode, SHA-256, 크기·MIME·확장자·Pixel 검증
- [x] multipart 요청 선처리 상한과 잘못된 Pillow 입력의 안정적 4xx 오류 매핑
- [x] Private MinIO 업로드, 실제 Object HEAD 메타데이터 검증과 Signed GET 구현
- [x] Storage·DB 실패 보상, 보상 실패 안전 관측과 실제 PostgreSQL·MinIO 통합 테스트
- [x] 다른 Tenant `404`, Role, 위장 파일, Signed Download를 포함한 E2E 검증
- [x] README, 핵심 설계 문서, ADR-0006~0008과 Sprint 1 Progress 동기화
- [x] Case/Evidence 접수에서 실제 LLM·Vision 분석을 시작하지 않음
- [x] 독립 Closeout에서 P1 3건과 P2 4건을 수정·검증하고 P0/P1 미해결 0 확인
- [x] Closeout 승인 범위의 로컬 기준점 Commit만 생성하고 Push하지 않음

## 5. GitHub 협업 구축 체크리스트

- [x] 연결 계정 `it0615` 확인
- [x] 경량 GitFlow와 브랜치 명명 규칙 문서화
- [x] PR 템플릿과 Issue Form 작성
- [x] 초기 CODEOWNERS를 `@it0615`로 지정
- [x] 모든 세션 종료 시 상태 문서를 갱신하도록 `AGENTS.md`에 규칙 추가
- [x] 초기 커밋 대상의 Secret·대용량·Binary 안전성 감사
- [x] 로컬 Git을 `main`으로 초기화
- [x] 로컬 Foundation 초기 커밋 `6fc20d3` 생성
- [x] 로컬 `develop` 장기 브랜치 생성
- [x] 조직 handle `CSightICT`와 저장소 `csight-core` 확정
- [x] GitHub 브라우저에서 `it0615` 로그인 확인
- [x] `CSightICT` 조직 생성 및 설정 권한 확인
- [x] Private `CSightICT/csight-core` 저장소 생성
- [x] GitHub 플러그인에 `CSightICT/csight-core`만 접근 승인
- [x] GitHub CLI OAuth에 `workflow` scope 승인
- [x] 원격 `main` Push
- [x] 원격 `develop` 장기 브랜치 생성
- [x] 원격 `chore/github-governance` 작업 브랜치 Push
- [x] 첫 GitHub Actions 성공 후 Required check Context `Quality and fast tests` 확정
- [x] Squash·Merge 허용, Rebase 비활성화, 병합 후 브랜치 삭제 설정
- [x] 거버넌스 PR #2를 `develop` 대상으로 생성
- [ ] `main`과 `develop` Branch protection 적용 — 현재 Private 플랜 제약으로 BLOCKED, Issue #1
- [ ] 팀·협업자 권한과 조직 단위 CODEOWNERS 갱신

## 6. 마지막 검증 원장

| 날짜 | 명령·검사 | 상태 | 실제 결과 |
|---|---|---|---|
| 2026-08-26 | `uv sync --frozen --group dev` | PASS | Python 3.12 환경과 lockfile 설치 |
| 2026-08-26 | Ruff / Ruff Format | PASS | 80 files |
| 2026-08-26 | Pyright strict | PASS | 0 errors, 0 warnings |
| 2026-08-26 | 기본 pytest | PASS | 37 passed |
| 2026-08-26 | Core Integration | PASS | 4 passed |
| 2026-08-26 | Architecture / Contract / E2E | PASS | 2 / 14 / 3 passed |
| 2026-08-26 | `make test-all` | PASS | 기본 37 + Integration 4 |
| 2026-08-26 | Compose와 Health 장애·복구 | PASS | 정상 200, RabbitMQ 장애 503, 복구 200 |
| 2026-08-26 | Git 초기 커밋 안전성 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, Ignore 적용 확인 |
| 2026-08-26 | 협업 문서 YAML | PASS | Issue Form 4개와 CI Workflow 파싱 |
| 2026-08-26 | Foundation 초기 커밋 | PASS | `main` commit `6fc20d3` |
| 2026-08-26 | GitHub 조직·Private 저장소 | PASS | `CSightICT/csight-core`, People 2명 확인 |
| 2026-08-26 | 원격 `main` Push | BLOCKED | OAuth App에 `workflow` scope가 없어 서버가 거부 |
| 2026-08-26 | GitHub CLI scope 갱신 1차 | FAIL | 장치 인증 Polling 중 HTTP 502, 재시도 필요 |
| 2026-08-26 | GitHub 플러그인 저장소 조회 | BLOCKED | `CSightICT/csight-core` 404, 설치 범위 밖 |
| 2026-08-26 | GitHub 원격 CI | NOT_RUN | 원격 브랜치가 아직 Push되지 않음 |
| 2026-08-26 | GitHub CLI scope 갱신 2차 | PASS | `repo`, `read:org`, `gist`, `workflow` scope 확인 |
| 2026-08-26 | 원격 브랜치 Push | PASS | `main`, `develop`, `chore/github-governance` 추적 브랜치 생성 |
| 2026-08-26 | ChatGPT Codex Connector 설치 | PASS | `CSightICT/csight-core` 단일 저장소 범위로 조회 확인 |
| 2026-08-26 | 초기 GitHub Actions | PASS | 세 브랜치 성공, Check Context `Quality and fast tests` |
| 2026-08-26 | 저장소 병합 설정 | PASS | Squash·Merge 허용, Rebase 비활성화, 병합 후 브랜치 삭제 |
| 2026-08-26 | `main`·`develop` 보호 규칙 API | BLOCKED | Private 저장소의 현재 플랜에서 HTTP 403 |
| 2026-08-26 | 보호 규칙 추적 Issue | PASS | Issue #1 생성 |
| 2026-08-26 | 거버넌스 PR 생성 | PASS | PR #2 Open, `chore/github-governance` → `develop` |
| 2026-08-26 | 거버넌스 PR 최신 CI | PASS | Head `7298cda`, Run `32867908663`, `Quality and fast tests` 성공 |
| 2026-08-26 | Sprint 1 Dependency 동기화 | PASS | `uv sync --frozen --group dev`, Lockfile 기준 설치 성공 |
| 2026-08-26 | Sprint 1 Ruff / Format | PASS | 전체 Lint 통과, 138 files already formatted |
| 2026-08-26 | Sprint 1 Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| 2026-08-26 | Sprint 1 `make test-all` | PASS | Fast 183 passed·18 deselected, Integration 18 passed·183 deselected |
| 2026-08-26 | Sprint 1 대상별 pytest | PASS | Unit 162, Architecture 4, Contract 14, 기존 E2E 3, HTTP API 15; 서로 중복 포함 |
| 2026-08-26 | Repository Tenant Scope | PASS | 모든 쓰기·조회 메서드 명시적 Tenant, 불일치 SQL 전 거부와 통합 검증 |
| 2026-08-26 | Case Idempotency 동시성 | PASS | PostgreSQL atomic `ON CONFLICT`, 동일 Tenant 중복 Case 1개 유지 |
| 2026-08-26 | 실제 PostgreSQL·MinIO 보상 | PASS | Partial write와 `AVAILABLE` 전환 실패 2건에서 Object 삭제·`FAILED` 확인 |
| 2026-08-26 | MinIO 대상 Integration | PASS | Private Signed/Unsigned 접근과 장애 보상 묶음 3 passed |
| 2026-08-26 | Private MinIO 접근 | PASS | Signed GET 성공, 서명 없는 동일 Object GET은 401/403 |
| 2026-08-26 | Tenant A/B HTTP E2E | PASS | 로그인·권한·Case·Evidence·Signed Download와 타 Tenant `404` |
| 2026-08-26 | Live HTTP Vertical Slice | PASS | 초기 17개 검사와 최종 이미지 재빌드 후 9개 Smoke 통과 |
| 2026-08-26 | Live Multipart 조기 상한 | PASS | Body 전송 전 `413 FILE_TOO_LARGE` 응답 확인 |
| 2026-08-26 | Alembic Upgrade / Head / Drift | PASS | `make migrate`, `20260826_0002 (head)`, 새 Upgrade 작업 없음 |
| 2026-08-26 | Raw Host Alembic | EXPECTED_FAIL | `.env` 미Export 직접 실행은 Fail-closed; 표준 `make migrate`·Compose 명령은 통과 |
| 2026-08-26 | Development Seed 2회 | PASS | 동일 Tenant·사용자·Role을 중복 생성하지 않고 Password Hash 유지 |
| 2026-08-26 | Final Compose Health | PASS | 최종 이미지 재빌드 후 API·Worker·PostgreSQL·RabbitMQ·MinIO 5개 Healthy |
| 2026-08-26 | 검증 데이터 정리 | PASS | Case·Evidence·History·Idempotency Row 0, MinIO Object 0 |
| 2026-08-26 | 독립 최종 감사 | PASS | 재현 가능한 P0·P1·P2 완료 차단 이슈 없음 |
| 2026-08-26 | `git diff --check` | PASS | Whitespace 오류 없음 |
| 2026-08-26 | Markdown 인계 검증 | PASS | 32 files, 로컬 Link 44개 존재, 불균형 Fence 0 |
| 2026-08-26 | Local 인증·Seed 값 누출 검사 | PASS | `.env` 밖에서 설정된 민감값 4개와 일치하는 내용 0 |
| 2026-08-26 | Sprint 1 Closeout 독립 감사 | PASS | P0 0, P1 3/3 수정, P2 4/4 보강, P0/P1 미해결 0 |
| 2026-08-26 | Closeout Ruff / Pyright | PASS | Lint 통과, Pyright 0 errors·0 warnings |
| 2026-08-26 | Closeout Format 후보 범위 | PASS | Sprint 1 Commit 후보 전체; 별도 미추적 Kaputt 문서 제외 |
| 2026-08-26 | Closeout `make test-all` | PASS | Fast 189 passed·18 deselected, Integration 18 passed·189 deselected |
| 2026-08-26 | Closeout 대상별 pytest | PASS | Unit 168, Architecture 4, Contract 14, 기존 E2E 3, HTTP API 15; 중복 포함 |
| 2026-08-26 | Closeout PostgreSQL / MinIO | PASS | PostgreSQL 대상 10, MinIO·보상 대상 3 |
| 2026-08-26 | 격리 Migration 수명주기 | PASS | 빈 DB→Head, Baseline→Head, Head→Baseline→Head, Drift와 복합 Tenant FK |
| 2026-08-26 | Closeout Compose·Seed | PASS | 이미지 Build, 장기 서비스 5개 Healthy, Seed 2회 |
| 2026-08-26 | Closeout Live HTTP | PASS | JWT, Case 201/Replay 200, Evidence, Signed GET, Object HEAD, A/B `404` |
| 2026-08-26 | 누락 Evidence Object | PASS | DB `AVAILABLE`이어도 URL `500 EVIDENCE_UPLOAD_FAILED` |
| 2026-08-26 | Closeout 검증 데이터 정리 | PASS | 업무 테이블 Row 0, MinIO Object 0, 임시 DB 2개 삭제 |
| 2026-08-26 | Closeout Commit 안전성 | PASS | `.env`·Secret·생성물·Kaputt 문서를 Stage하지 않고 로컬 Commit만 생성 |

## 7. 미해결 사항과 사용자 결정

- 저장소를 Private로 유지하는 현재 플랜에서는 `main`·`develop` Branch protection API가
  HTTP 403을 반환한다. 저장소 공개 전환 없이 지원 플랜을 적용할지 Issue #1에서 결정한다.
- `kimhrin`은 현재 저장소 `read` 권한이라 보호 규칙의 필수 승인으로 인정되는
  write-access reviewer가 아니다. 명시적인 사용자 결정 전에는 권한을 올리지 않으며,
  필요하면 `write` 이상과 팀 구성을 별도로 승인한다.
- 초기에는 `@it0615`가 유일한 CODEOWNER다. 리뷰 가능한 구성원이 정해지면 조직 팀으로
  교체한다.
- Sprint 1은 Evidence 업로드 Idempotency, 강제 종료 뒤 `PENDING`·고아 Object 자동
  Reconciliation, Idempotency 만료 Cleanup·Key 재사용을 제공하지 않는다.
- 이미지 EXIF 제거·재인코딩·개인정보 마스킹·Virus Scan과 고객 원문·원본·Audit의
  Retention·삭제 정책은 실제 데이터 반입 전에 결정해야 한다.
- Refresh Token·Revocation·OIDC/SSO·PostgreSQL RLS와 Production MinIO Gateway,
  Secret Rotation, Edge 동시 업로드 제한은 후속 운영 범위다.
- 실제 LLM·Vision, Analysis Run, 비동기 `202`, Policy·Routing·Review·Report·RAG는
  구현하지 않았고 Case/Evidence 접수로 자동 시작되지 않는다.
- 실제 제품 측 결정인 결함 Taxonomy, 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는
  다음 Sprint의 ADR 대상으로 남아 있다.
- Sprint 1 Closeout은 `feature/sprint-1-case-evidence`의 로컬 기준점 Commit으로 확정하며
  Push하지 않았다. 이 브랜치는 아직 병합되지 않은 거버넌스 작업을 기반으로 한다.
- 루트의 미추적 `kaputt_best_vision_architecture.md`는 Sprint 1과 무관한 사용자 작업물이다.
  Closeout에서 수정·삭제·Stage하지 않았으며 후속 소유 작업에서 별도로 다룬다.

## 8. 다음 실행 항목

- [x] Sprint 1 Diff를 독립 Closeout 감사하고 로컬 기준점 Commit을 생성한다.
- [ ] 사용자가 Push·PR을 별도로 승인할 때까지 로컬 Commit을 원격에 전송하지 않는다.
- [ ] 원격 작업 전 거버넌스 PR #2 병합 또는 Sprint 1 Branch 재정렬 순서를 결정한다.
- [ ] PR #2에 유효한 사람 리뷰와 승인을 확보한다.
- [ ] GitHub Private 저장소 Branch protection을 지원하는 플랜 적용 여부를 결정한다.
- [ ] `kimhrin`에게 승인 리뷰가 가능한 권한을 부여할지, 조직 팀을 만들지 결정한다.
- [ ] 플랜·리뷰어 결정 후 Issue #1의 목표 규칙을 `main`과 `develop`에 적용한다.
- [ ] 정책에 맞는 유효 승인 또는 명시적인 Bootstrap 예외 결정 후 PR #2를 `develop`에
  병합한다.
- [ ] 별도 Sprint 2 지시를 받은 뒤 Append-only Analysis Run, `202 Accepted`, 얇은 Celery
  Use Case, Retry·Timeout·재전달 Idempotency와 모델·Prompt·Policy 버전을 연결한다.
- [ ] Evidence Reconciliation·Orphan Cleanup·업로드 Idempotency와 Retention 정책을
  우선순위에 따라 별도 작업으로 계획한다.

## 9. 세션 종료 체크리스트

- [x] 변경한 파일과 목적을 기록했다.
- [x] 실제 실행한 검증 명령과 결과만 기록했다.
- [x] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [x] 외부 서비스 상태에 관측 날짜를 붙였다.
- [x] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [x] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [x] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [x] 아래 세션 로그를 추가했다.

## 10. 세션 로그

### 2026-08-26 — Sprint 0 Foundation 완료

- 목표: 실행 가능한 FastAPI/Celery/PostgreSQL/RabbitMQ/MinIO Foundation 구축
- 완료: API, Port/Adapter, Mock AI, Migration, Worker, Compose, CI, 테스트, 문서
- 검증: 기본 37건과 Integration 4건을 포함한 `make test-all`, 실제 장애·복구 경로 통과
- 미실행: GitHub 원격 CI
- 다음 작업: GitHub 협업 기반 생성 후 Sprint 1 Case/Evidence 경계 구현

### 2026-08-26 — GitHub 협업 기반 준비

- 목표: 조직 저장소, 장기 브랜치, PR 중심 협업, 세션 간 인계 체계 구축
- 완료: GitHub 계정 확인, 브랜치 정책, 기여 규칙, PR·Issue 템플릿, 체크리스트,
  초기 커밋 안전성 감사, 로컬 `main`·`develop`, `CSightICT` 조직과 Private
  `CSightICT/csight-core` 저장소
- 검증: GitHub 플러그인에서 연결 계정 `it0615` 확인, 새 조직 미존재 확인. 고신뢰
  Secret과 5 MiB 초과 커밋 후보가 없고 Issue Form YAML이 파싱됨을 확인. Ruff, Format,
  Pyright, 기본 37건과 Core Integration 4건 재통과
- Blocker: GitHub CLI OAuth App의 `workflow` scope 부족. 장치 인증 1차 시도는 HTTP 502
- 다음 작업: OAuth scope 갱신 재시도, 원격 Push, 첫 CI, Branch protection 적용

### 2026-08-26 — GitHub 연결 승인 및 원격 거버넌스 구축

- 목표: 승인된 `workflow` scope와 `CSightICT` 커넥터 연결로 원격 협업 경로를 활성화
- 완료: CLI `workflow` scope, 저장소 단위 Connector 설치, 세 원격 브랜치, 초기 CI,
  병합 방식 설정, 보호 규칙 추적 Issue #1, 거버넌스 PR #2
- 검증: GitHub 플러그인에서 Private 저장소 조회 성공. `main`, `develop`, 작업 브랜치의
  초기 Actions와 PR #2 Head `7298cda` Run `32867908663`이 성공하고 Check Context가
  `Quality and fast tests`임을 확인
- Blocker: Private 저장소의 현재 플랜은 Branch protection API를 HTTP 403으로 거부.
  `kimhrin`은 현재 `read` 권한이며 승인 없이 권한을 변경하지 않음
- 다음 작업: PR #2 사람 리뷰, 지원 플랜과 리뷰어 권한 결정, Issue #1 이행

### 2026-08-26 — Sprint 1 Case & Evidence Vertical Slice 완료

- 목표: 인증된 Tenant 사용자의 Case 접수부터 Private 이미지 Evidence와 Signed GET까지
  실제 PostgreSQL·MinIO 기반 End-to-End 경로 완성
- Branch: `feature/sprint-1-case-evidence`; 모든 변경은 미커밋이며 Commit·Push하지 않음
- 완료: Local Seed, Argon2id·HS256 인증, 현재 Role 재조회, Principal Tenant Scope,
  Case 생성·조회·이력·Idempotency, 이미지 검증·요청 상한, Private MinIO, 실제 HEAD
  무결성 확인, Signed URL, 실패 보상·안전 관측, Migration, API·운영 문서와 ADR-0006~0008
- 검증: Ruff, 138-file Format, Pyright 0, Fast 183건, 실제 Core Integration 18건,
  Tenant A/B E2E, 실제 MinIO/PostgreSQL 보상 2건, 최종 Live HTTP 9개와 Multipart 413,
  Migration Head·Drift, Seed 2회, 5개 장기 서비스 Healthy
- 정리: 테스트 업무 Row와 MinIO Object가 모두 0임을 확인하고 Core 서비스는 Healthy로 유지
- 감사: 독립 재검토에서 재현 가능한 P0·P1·P2 완료 차단 이슈 없음
- 제한: 자동 분석, Evidence Idempotency·Reconciliation, EXIF·악성코드 처리, Retention,
  OIDC·RLS와 Production Edge·Secret 운영은 후속 범위
- 다음 작업: 사용자 Diff 검토 후 별도 승인 시 Commit·Push·PR, 이후 Sprint 2 Analysis Run

### 2026-08-26 — Sprint 1 Closeout 독립 감사 및 로컬 기준점

- 목표: 미커밋 Sprint 1 전체 Diff를 기존 완료 보고와 독립적으로 재검토하고 재현 가능한
  로컬 기준점으로 확정
- 발견: P0 0, P1 3, P2 4. 타 Tenant Viewer 업로드 오류 우선순위, SQL Echo Bind 값,
  누락 Object Signed URL을 P1으로 확인
- 수정: Tenant `404` 우선, SQL Parameter 은닉, URL 전 Object HEAD, 빈 Allowlist
  Fail-closed와 Tenant·Animated·Hard Bomb 회귀 테스트
- 검증: Pyright 0, Fast 189, Integration 18, Unit 168, Contract 14, Architecture 4,
  기본 E2E 3, HTTP API 15, 격리 Migration 3경로·Drift·복합 FK, Compose 5개 Healthy,
  Seed 2회, 실제 JWT→Case Replay→Evidence→Signed GET→Object HEAD→Tenant A/B `404`
- 정리: 업무 Row 0, MinIO Object 0, UUID 기반 임시 DB 2개 삭제
- Git: 정확한 Sprint 1 후보만 로컬 Commit, Push·PR 없음. 범위 밖 미추적 Kaputt 문서는
  사용자 파일로 보존
- 다음 작업: 별도 승인 전 Push 금지; 원격 전 PR #2/Branch 순서 결정; 별도 지시 후 Sprint 2
