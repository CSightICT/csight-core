# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 Sprint 0 증거는 `SPRINT_0_FOUNDATION.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 0 — Foundation |
| 진행 중 작업 | GitHub 거버넌스 PR 검증·리뷰 및 보호 브랜치 플랜 결정 |
| 마지막 갱신일 | 2026-08-26, Asia/Seoul |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | `CSightICT/csight-core` — Private, `main`·`develop`·거버넌스 작업 브랜치 Push 완료 |
| 로컬 Git | `main`·`develop`, 작업 브랜치 `chore/github-governance`, 거버넌스 PR #2 Open |
| 마지막 런타임 관측 | 2026-08-26, Core 장기 서비스 5개 Healthy — 다음 세션에서 재확인 필요 |

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

## 4. GitHub 협업 구축 체크리스트

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

## 5. 마지막 검증 원장

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

## 6. 미해결 사항과 사용자 결정

- 저장소를 Private로 유지하는 현재 플랜에서는 `main`·`develop` Branch protection API가
  HTTP 403을 반환한다. 저장소 공개 전환 없이 지원 플랜을 적용할지 Issue #1에서 결정한다.
- `kimhrin`은 현재 저장소 `read` 권한이라 보호 규칙의 필수 승인으로 인정되는
  write-access reviewer가 아니다. 명시적인 사용자 결정 전에는 권한을 올리지 않으며,
  필요하면 `write` 이상과 팀 구성을 별도로 승인한다.
- 초기에는 `@it0615`가 유일한 CODEOWNER다. 리뷰 가능한 구성원이 정해지면 조직 팀으로
  교체한다.
- 실제 제품 측 결정인 결함 Taxonomy, 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는
  다음 Sprint의 ADR 대상으로 남아 있다.

## 7. 다음 실행 항목

- [ ] PR #2에 유효한 사람 리뷰와 승인을 확보한다.
- [ ] GitHub Private 저장소 Branch protection을 지원하는 플랜 적용 여부를 결정한다.
- [ ] `kimhrin`에게 승인 리뷰가 가능한 권한을 부여할지, 조직 팀을 만들지 결정한다.
- [ ] 플랜·리뷰어 결정 후 Issue #1의 목표 규칙을 `main`과 `develop`에 적용한다.
- [ ] 정책에 맞는 유효 승인 또는 명시적인 Bootstrap 예외 결정 후 PR #2를 `develop`에
  병합한다.
- [ ] Sprint 1에서 Case/Evidence CRUD와 append-only 분석 영속화를 시작한다.

## 8. 세션 종료 체크리스트

- [x] 변경한 파일과 목적을 기록했다.
- [x] 실제 실행한 검증 명령과 결과만 기록했다.
- [x] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [x] 외부 서비스 상태에 관측 날짜를 붙였다.
- [x] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [x] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [x] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [x] 아래 세션 로그를 추가했다.

## 9. 세션 로그

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
