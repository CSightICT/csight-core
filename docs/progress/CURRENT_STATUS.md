# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 Sprint 0 증거는 `SPRINT_0_FOUNDATION.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 0 — Foundation |
| 진행 중 작업 | GitHub 조직·저장소·협업 정책 구축 |
| 마지막 갱신일 | 2026-08-26, Asia/Seoul |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | 아직 생성되지 않음 |
| 로컬 Git | `main`으로 초기화, 초기 커밋 후보 Staged |
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
| 로컬 Git 초기화 | PASS | 빈 저장소를 `main`으로 초기화하고 커밋 후보 Staged |
| GitHub 조직·저장소 | BLOCKED | 조직 handle 확정 및 GitHub 브라우저 로그인 필요 |
| 원격 브랜치·보호 규칙 | BLOCKED | 원격 저장소와 첫 CI 성공 실행 필요 |

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
- [ ] GitHub Actions 원격 실행

## 4. GitHub 협업 구축 체크리스트

- [x] 연결 계정 `it0615` 확인
- [x] 경량 GitFlow와 브랜치 명명 규칙 문서화
- [x] PR 템플릿과 Issue Form 작성
- [x] 초기 CODEOWNERS를 `@it0615`로 지정
- [x] 모든 세션 종료 시 상태 문서를 갱신하도록 `AGENTS.md`에 규칙 추가
- [x] 초기 커밋 대상의 Secret·대용량·Binary 안전성 감사
- [x] 로컬 Git을 `main`으로 초기화
- [ ] 조직 handle과 저장소 이름·공개 범위 확정
- [ ] GitHub 브라우저 로그인
- [ ] 조직 생성 및 소유자 확인
- [ ] Private 저장소 생성
- [ ] 로컬 `main` 초기 커밋
- [ ] 원격 `main` Push
- [ ] `develop` 장기 브랜치 생성
- [ ] `main`과 `develop` Branch protection 적용
- [ ] 첫 GitHub Actions 성공 후 Required check Context 확정
- [ ] 팀·협업자 권한과 조직 단위 CODEOWNERS 갱신

## 5. 마지막 검증 원장

| 날짜 | 명령·검사 | 상태 | 실제 결과 |
|---|---|---|---|
| 2026-08-26 | `uv sync --frozen --group dev` | PASS | Python 3.12 환경과 lockfile 설치 |
| 2026-08-26 | Ruff / Ruff Format | PASS | 76 files |
| 2026-08-26 | Pyright strict | PASS | 0 errors, 0 warnings |
| 2026-08-26 | 기본 pytest | PASS | 37 passed |
| 2026-08-26 | Core Integration | PASS | 4 passed |
| 2026-08-26 | Architecture / Contract / E2E | PASS | 2 / 14 / 3 passed |
| 2026-08-26 | `make test-all` | PASS | 기본 37 + Integration 4 |
| 2026-08-26 | Compose와 Health 장애·복구 | PASS | 정상 200, RabbitMQ 장애 503, 복구 200 |
| 2026-08-26 | GitHub 원격 CI | NOT_RUN | 원격 저장소 미생성 |

## 6. 미해결 사항과 사용자 결정

- GitHub 조직 handle이 필요하다. 기본 제안은 `csight-ai-platform`이다.
- 저장소 기본 제안은 `csight-core`, 공개 범위는 Private이다.
- GitHub 조직 생성 화면에 로그인해야 한다.
- 초기에는 `@it0615`가 유일한 CODEOWNER다. 구성원이 정해지면 조직 팀으로 교체한다.
- 실제 제품 측 결정인 결함 Taxonomy, 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는
  다음 Sprint의 ADR 대상으로 남아 있다.

## 7. 다음 실행 항목

1. 조직 handle과 저장소 이름·공개 범위를 사용자에게 확정받는다.
2. 품질 검증 후 Foundation 초기 커밋을 만든다.
3. GitHub 조직과 Private 저장소를 생성하고 `main`, `develop`을 Push한다.
4. 첫 CI 성공 후 두 장기 브랜치에 보호 규칙을 적용한다.
5. Sprint 1에서 Case/Evidence CRUD와 append-only 분석 영속화를 시작한다.

## 8. 세션 종료 체크리스트

- [ ] 변경한 파일과 목적을 기록했다.
- [ ] 실제 실행한 검증 명령과 결과만 기록했다.
- [ ] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [ ] 외부 서비스 상태에 관측 날짜를 붙였다.
- [ ] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [ ] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [ ] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [ ] 아래 세션 로그를 추가했다.

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
  초기 커밋 안전성 감사, 로컬 `main` 초기화
- 검증: GitHub 플러그인에서 연결 계정 `it0615` 확인, 새 조직 미존재 확인. 고신뢰
  Secret과 5 MiB 초과 커밋 후보가 없고 Issue Form YAML이 파싱됨을 확인
- Blocker: 조직 handle 미확정, 브라우저 GitHub 로그인 필요
- 다음 작업: Git 안전성 감사 후 로컬 초기화, 조직·저장소 생성, Push, 보호 규칙 적용
