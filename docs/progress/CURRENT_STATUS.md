# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 구현 증거는 `SPRINT_0_FOUNDATION.md`와
`SPRINT_1_CASE_EVIDENCE.md`, 독립 감사 증거는 `SPRINT_1_CLOSEOUT.md`, 현재 분석 경로는
`SPRINT_2_ANALYSIS_LLM.md`, 독립 감사 원장 `SPRINT_2_CLOSEOUT.md`, 실제 모델 기록
`SPRINT_2_5_QWEN38_SERVING.md`와 현재 `SPRINT_3_VISION_ANALYSIS.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 4A Closeout — `PASS`, 미해결 P0/P1 0 |
| 진행 중 작업 | 승인된 Sprint 4A 범위만 로컬 Commit 후 Sprint 4B 전용 Branch 생성 |
| 마지막 갱신일 | 2026-08-26, Asia/Seoul |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | `CSightICT/csight-core` — Private, Sprint 2·2.5 변경 Push 금지 |
| 로컬 Git | `feature/sprint-4a-llm-reference-data`, Base `330cbdb`, Closeout Commit 직전 |
| 마지막 런타임 관측 | 2026-08-26, Core 6개 Network-free Mock, Migration `0005`, Queue 0 |

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
| Sprint 2 Analysis·LLM | PASS | Append-only Run/Attempt/Result, Outbox, Celery, Mock, vLLM Adapter, API |
| Sprint 2 Migration·Live | PASS | Head `20260826_0003`, 격리 왕복·Drift, 실제 RabbitMQ Mock Vertical Slice |
| Sprint 2 복구·멱등성 | PASS | Replay/Conflict, Duplicate 1 Result, Lease Recovery·Fencing·Max Attempt 종결 |
| Sprint 2 독립 Closeout | PASS | P0/P1 미해결 0, 정적·회귀·Migration·Docker·Live Gate 재통과 |
| Sprint 2.5 Qwen3.8 실제 서빙 | QUALIFIED_WITH_LIMITATIONS | 4090 Cold Start 2회, 26분 안정성, 안전 Gate와 실제 Backend E2E 통과; Action/Missing 품질 제한 |
| Sprint 3 Vision·Multimodal | MOCK_QUALIFIED | Canonical Vision, Snapshot, Text/Vision fan-out/join, Partial Success와 live Mock E2E 통과 |
| Sprint 3 실제 Vision | NOT_AVAILABLE | Endpoint/model/sample 미제공; `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE` 1건 |
| Sprint 4A LLM Contract v2 | PASS | v1 보존, v2 Prompt/Schema/Persistence/API와 live Mock 통과 |
| Sprint 4A Policy Reference | PASS | 합성 2 Tenant, 24 Document, 168 Clause, retired 6 |
| Sprint 4A Evaluation Data | PASS | 160/120/50/30/10, Gold missing·cross-tenant 0 |
| Sprint 4A 실제 Qwen 평가 | SKIPPED | Endpoint 미사용; `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| Sprint 4A 독립 Closeout | PASS | P0/P1 0, 정적·전체 회귀·데이터·Migration·Docker 재검증 |
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

## 5. Sprint 2 완료 체크리스트

- [x] Sprint 1 기준점 `244c282`에서 `feature/sprint-2-analysis-llm` Branch 생성
- [x] Case와 분리된 Append-only Analysis Run·Stage·Attempt·Result 계약 구현
- [x] Code Prompt Manifest, Content Hash, Strict Schema와 정확한 Source Quote 검증
- [x] 결정적 Mock과 OpenAI-compatible vLLM JSON Schema Adapter 구현
- [x] Run·Stage·Idempotency·Outbox 원자적 생성과 여섯 ID Queue Payload 적용
- [x] `FOR UPDATE SKIP LOCKED` Dispatcher와 Claim Token·Lease Fencing Worker 구현
- [x] Transient Backoff, Permanent Failure, Max Attempt, Worker Lost·Timeout 복구 구현
- [x] POST 202/Replay 200/Conflict 409, 목록·상세, Case Latest Analysis 연결
- [x] Tenant `404`, 역할 권한, Raw Prompt·Response·Secret 비보존 검증
- [x] 기존 Revision 불변의 `20260826_0003` Migration과 여섯 테이블 구현
- [x] Ruff, 158-file Format, Pyright 0, Fast 291, Core Integration 31 통과
- [x] 실제 Docker Login→Case→Outbox→RabbitMQ→Celery→SUCCEEDED와 중복 전달 통과
- [x] 격리 Migration 왕복·Drift, 검증 행·임시 DB 정리, 장기 서비스 6개 Healthy 확인
- [x] README, 핵심 설계 문서 03–10, ADR-0009~0011, Progress 문서 동기화
- [x] Vision·Alignment·Policy·Routing·Review·Report·RAG를 구현하지 않음
- [x] 독립 Closeout에서 P0/P1 미해결 0과 전체 Gate 재통과 확인
- [x] 승인된 Sprint 2 로컬 Commit만 생성하고 Push·PR은 만들지 않음
- [x] 미추적 Kaputt 문서를 수정·삭제·Stage하지 않고 보존

## 5.1. Sprint 2.5 완료 체크리스트

- [x] Sprint 2 Commit `294cb5b`에서 전용 Branch 생성, Push·PR 없음
- [x] Qwen3.8 Artifact revision과 vLLM image digest 고정
- [x] RTX 4090 환경·기존 Process·Disk·RAM·Private Network 감사
- [x] Tailscale private bind와 `VLLM_API_KEY` 환경변수 인증; 노출 일회용 Key 즉시 회전
- [x] Text-only, Vision modality 0, 서버·요청 non-thinking 이중 설정
- [x] Cold Start 2회, `/v1/models`, 26분 Stability, OOM/Error/Restart 0
- [x] 100건 합성 평가와 Prompt 1.0.1 개선 후 안전 Gate 전부 통과
- [x] Human Spot-check 20건과 성능 Profile A–D, Peak VRAM 측정
- [x] 실제 외부 GPU 5건 Skip 0, Backend E2E 성공 Run 10
- [x] Model/Revision/Prompt DB Snapshot, Duplicate No-op, Timeout Retry·Max 확인
- [x] Raw Prompt/Response/Reasoning Column 0, unsafe Outbox Payload 0
- [x] 합성 Data·Queue·Orphan 0, Core Worker 기본 Mock과 6개 Health 복구
- [x] README, 설계 03·05·06·08·09·10, ADR-0012, Manifest와 Progress 동기화
- [x] 이 문서를 포함한 로컬 Commit `chore: qualify qwen3.8 27b serving on single 4090` 생성;
  정확한 SHA는 `git log -1`과 최종 인계에서 확인

## 5.2. Sprint 3 완료 체크리스트

- [x] Base `7d63cbb` 확인 후 `feature/sprint-3-vision-analysis` Branch 생성
- [x] Qwen 평가 taxonomy/metric/empty-set 감사와 diagnostics regression
- [x] Canonical Vision schema, tri-state quality, normalized bbox, native taxonomy mapping
- [x] 10개 deterministic Mock와 private multipart Remote Adapter
- [x] `analysis_run_evidence` Snapshot, bounded MinIO read와 SHA-256 검증
- [x] `vision_analysis_results`/`vision_detections` image별 append-only persistence
- [x] Text-only 호환과 multimodal Text/Vision independent Outbox fan-out
- [x] Application-level join, `PARTIAL_SUCCESS`, partial result 보존과 retry
- [x] 병렬 Run CAS 경쟁에서 Stage 고립 방지 및 live 재검증
- [x] `20260826_0004` empty/previous/downgrade-upgrade/drift Migration Gate
- [x] API detail `vision_results`/`failed_stages`, no-image 422
- [x] PostgreSQL/MinIO/RabbitMQ/tenant/duplicate/retry/partial Mock E2E
- [x] ADR-0013~0017, 설계 03~10, README와 Sprint 3 Progress 동기화
- [x] Ruff, Format 167, Pyright 0, Fast 328, Core Integration 36
- [x] Docker 6개 Healthy, Queue 0, 합성 Case 5/Object 4 정리
- [x] 외부 Vision은 실제 endpoint 미제공을 숨기지 않고 1건 Skip
- [x] 독립 Closeout에서 P0/P1 미해결 0과 전체 Gate 재통과
- [x] Push·PR 없음, Kaputt 사용자 파일 미수정·미Stage

## 5.3. Sprint 4A 완료 체크리스트

- [x] Sprint 3 Closeout Commit `330cbdb`, Push·PR 없음, Kaputt 파일 제외
- [x] `feature/sprint-4a-llm-reference-data` Branch 생성
- [x] Text Extraction v1 호환과 v2 Pipeline/Prompt/Schema `2.0.0/2.0.0/2.0`
- [x] Declared/Extracted action과 Text/System missing 책임 분리
- [x] Completeness/action consistency rule `1.0.0`과 exact requested-action quote
- [x] 기존 v1 table 불변의 append-only v2 child Migration `20260826_0005`
- [x] Policy Query Builder/Grounded Explanation design-only Prompt/Schema
- [x] 합성 Policy Corpus 2 Tenant, 24 Document, 168 Clause, retired 6
- [x] Extraction 160, Retrieval 120, Grounding 50, Injection 30, Demo 10
- [x] Stable build/hash, manifest, quality/coverage report와 Make commands
- [x] ADR-0018~0025, data guide 4개, 설계 03~10과 README 갱신
- [x] 실제 Docker v2 Mock `SUCCEEDED`와 합성 row/queue 정리
- [x] Sprint 4A 최종 전체 Gate 실측값 확정
- [x] Sprint 4A Commit·Push·PR 없음, Kaputt 파일 미수정·미Stage

## 6. GitHub 협업 구축 체크리스트

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

## 7. 마지막 검증 원장

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
| 2026-08-26 | Sprint 2 시작 Baseline | PASS | Fast 189 passed·18 deselected, Integration 18 passed·189 deselected |
| 2026-08-26 | Sprint 2 Ruff / Format | PASS | Lint 통과, Python 대상 158 files already formatted |
| 2026-08-26 | Sprint 2 Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| 2026-08-26 | Sprint 2 기본 pytest | PASS | 291 passed·36 deselected·0 failed |
| 2026-08-26 | Sprint 2 Core Integration | PASS | 31 passed·5 external skipped·291 deselected·0 failed |
| 2026-08-26 | Sprint 2 Analysis Focus | PASS | Fast 76 passed·251 deselected; Integration 13 passed·5 skipped·309 deselected |
| 2026-08-26 | Sprint 2 Unit / Contract / Architecture | PASS | 227 passed·100 deselected / 45·282 / 4·0 |
| 2026-08-26 | Sprint 2 HTTP / RabbitMQ·Outbox / E2E | PASS | 29·0 / 18 passed·309 deselected / 6·321 |
| 2026-08-26 | Sprint 2 Migration Unit | PASS | 6 passed·0 failed |
| 2026-08-26 | Sprint 2 External vLLM | SKIPPED | 외부 Endpoint 미설정; 5 skipped·322 deselected, 호출 0 |
| 2026-08-26 | Sprint 2 PostgreSQL App E2E | PASS | 8 passed; Retry·Duplicate·Worker Lost·Lease Max·Fencing 포함 |
| 2026-08-26 | Sprint 2 격리 Migration | PASS | Empty→0003, 0003→0002→0003, Empty→0002→0003, Drift 없음 |
| 2026-08-26 | Sprint 2 Docker Build·Migration·Seed | PASS | 최종 이미지 Build, Head 적용, Development Seed 성공 |
| 2026-08-26 | Sprint 2 Live HTTP·Async | PASS | 202, Replay 200, Conflict 409, Tenant 404, Mock `SUCCEEDED` |
| 2026-08-26 | Sprint 2 Live Duplicate | PASS | 같은 Celery Message 재전달 뒤 Attempt 1·Result 1 유지 |
| 2026-08-26 | Sprint 2 Runtime Health | PASS | API·Worker·Dispatcher·PostgreSQL·RabbitMQ·MinIO 6개 Healthy |
| 2026-08-26 | Sprint 2 Queue·검증 데이터 정리 | PASS | Queue 0, Analysis 6개 Table 0, 합성 Case/Tenant 0, MinIO Object 0 |
| 2026-08-26 | Sprint 2 `git diff --check` | PASS | Whitespace 오류 없음 |
| 2026-08-26 | Sprint 2 Git 안전성 | PASS | Closeout 전 Commit·Push 0, 사용자 Kaputt 문서 수정·Stage·삭제 0 |
| 2026-08-26 | Sprint 2 독립 Closeout | PASS | P0 0, P1 0; 정적·291 Fast·31 Integration·세 Migration·Docker·Live 재통과 |
| 2026-08-26 | Sprint 2 Closeout Commit | PASS | `294cb5b`, 승인 범위 로컬 Commit; Push·PR 없음 |
| 2026-08-26 | Qwen Artifact·Runtime | PASS | revision 고정, vLLM 0.26.0 digest, Transformers 5.14.1, CUDA 13.0 |
| 2026-08-26 | Qwen Cold Start | PASS | 첫 Ready 8m06s, cache-hit Ready 97s, 동일 Profile 재현 |
| 2026-08-26 | Qwen Stability | PASS | 26m19s, Restart·OOM·Error 0, Healthy |
| 2026-08-26 | Qwen Quality Prompt 1.0.0 | FAIL | Pydantic 98%; multi-defect 중복 Enum 2건 재현 |
| 2026-08-26 | Qwen Quality Prompt 1.0.1 | PASS | 100건 Schema/Pydantic/Quote 100%, forbidden/injection/reasoning 0 |
| 2026-08-26 | Qwen Classification Baseline | LIMITATION | Issue F1 0.95, Action Accuracy 0.23, Missing F1 0.00 |
| 2026-08-26 | Qwen Spot-check | PASS_WITH_LIMITS | 안전 20/20, Issue 19/20, Action 10/20, Missing 8/20 |
| 2026-08-26 | Qwen Performance A–D | PASS | 30요청 성공, Timeout/OOM/Schema 실패 0; Peak 23,825 MiB |
| 2026-08-26 | 실제 External vLLM | PASS | 5 passed, 322 deselected, Skip 0 |
| 2026-08-26 | 실제 Qwen Backend E2E | PASS | 성공 Run/Result/Attempt 10/10/10, 고정 Metadata Snapshot |
| 2026-08-26 | Qwen Duplicate·Timeout | PASS | 재전달 Result/Attempt 1/1; Timeout Retry 후 Attempt 2 Max 종결 |
| 2026-08-26 | Sprint 2.5 정리·복구 | PASS | 합성 Case/Run 22 삭제, Queue/Orphan 0, Core 6개 Mock Healthy |
| 2026-08-26 | Sprint 2.5 최종 회귀 | PASS | Ruff, Format 162, Pyright 0, Fast 291, Integration 31 |
| 2026-08-26 | Sprint 3 시작 Baseline | PASS | Base `7d63cbb`; Fast 291 passed·36 deselected, Integration 31 passed·5 skipped·291 deselected |
| 2026-08-26 | Sprint 3 LLM 평가 감사 | PASS_WITH_LIMITS | Enum/PRF 수식 일치; Action input/gold 의미 모호, Missing support 진단 추가, 재평가 미실행 |
| 2026-08-26 | Sprint 3 Ruff / Format / Pyright | PASS | Ruff 0, Format 167 files, Pyright 0 errors·0 warnings |
| 2026-08-26 | Sprint 3 Fast Suite | PASS | 328 passed·42 deselected·0 failed |
| 2026-08-26 | Sprint 3 Core Integration | PASS | 36 passed·5 external-vLLM skipped·329 deselected·0 failed |
| 2026-08-26 | Sprint 3 Architecture·Contract·E2E | PASS | 합계 55 passed·0 failed; 기본 외부 호출 0 |
| 2026-08-26 | Sprint 3 PostgreSQL Multimodal E2E | PASS | Success, 양방향 Partial, Both Fail, Timeout Retry, Duplicate, Tenant 격리 5 tests |
| 2026-08-26 | Sprint 3 MinIO bounded read | PASS | 실제 Object read와 max size rejection 1 test |
| 2026-08-26 | Sprint 3 Migration lifecycle | PASS | Empty→0004, 0004→0003→0004, previous→0004, drift 0 |
| 2026-08-26 | Sprint 3 Live HTTP success | PASS | Login→PNG→Text success→2-Stage Multimodal success, Vision Result/Detection 각 1 |
| 2026-08-26 | Sprint 3 Live partial | PASS | 병렬 CAS 결함 수정 후 Text success/Vision permanent failure→`PARTIAL_SUCCESS` |
| 2026-08-26 | Sprint 3 Live no image | PASS | HTTP 422 `IMAGE_EVIDENCE_REQUIRED` |
| 2026-08-26 | Sprint 3 External Vision | SKIPPED | 1 skipped·369 deselected; `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE` |
| 2026-08-26 | Sprint 3 Docker·Queue | PASS | API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6개 Healthy; ready/unacked 0 |
| 2026-08-26 | Sprint 3 정리 | PASS | 합성 Case 5개와 private MinIO Object 4개 제거, 대상 Case 0 |
| 2026-08-26 | Sprint 3 Git 안전성 | PASS | `git diff --check`; Commit·Push·PR 0, Kaputt 파일 미수정·미Stage |
| 2026-08-26 | Sprint 3 Closeout 재감사 | PASS | P0/P1 0, Ruff, Format 165, Pyright 0, Fast 328, Integration 36 |
| 2026-08-26 | Sprint 3 Closeout Migration | PASS | empty→0004, 0004→0003→0004, 0003→0004, 두 DB drift 0 |
| 2026-08-26 | Sprint 3 Closeout Runtime | PASS | Core 6개 Healthy, HTTP ready, analysis queue ready/unacked 0 |
| 2026-08-26 | Sprint 3 Closeout Commit | PASS | `330cbdb feat: complete multimodal vision analysis pipeline`, Push·PR 없음 |
| 2026-08-26 | Sprint 4A LLM v2 Focus | PASS | v2/Corpus Unit 21, Prompt hash와 completeness/action/source quote |
| 2026-08-26 | Sprint 4A Policy Corpus | PASS | Build/validate 24 Document, 168 Clause, Tenant 2, duplicate 0 |
| 2026-08-26 | Sprint 4A Evaluation Data | PASS | 160/120/50/30/10, Gold missing 0, cross-tenant 0 |
| 2026-08-26 | Sprint 4A Migration 첫 시도 | FAIL | 오래된 Docker image가 `0005` 미포함; DB not up to date 감지 |
| 2026-08-26 | Sprint 4A Migration 재실행 | PASS | image rebuild 후 `0004→0005`, Alembic drift 0 |
| 2026-08-26 | Sprint 4A Live v2 Mock | PASS | Run SUCCEEDED, action 2, MULTIPLE_EXTRACTED, rule 1.0.0 |
| 2026-08-26 | Sprint 4A Live 정리 | PASS | 합성 Case/Run 관련 row 제거, RabbitMQ analysis 0/0 |
| 2026-08-26 | Sprint 4A 실제 Qwen | SKIPPED | Endpoint 미사용; `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| 2026-08-26 | Sprint 4A Stable Build | PASS | Policy·Evaluation aggregate hash가 반복 Build 전후 동일 |
| 2026-08-26 | Sprint 4A Static | PASS | Ruff, Format 179, Pyright 0 errors·warnings |
| 2026-08-26 | Sprint 4A Fast Regression | PASS | 354 passed, 42 deselected, 외부 호출 없음 |
| 2026-08-26 | Sprint 4A 대상별 Test | PASS | Unit 294, Architecture 4, Contract 50, E2E 6; 중복 포함 |
| 2026-08-26 | Sprint 4A Core Integration | PASS | 36 passed, external GPU 5 skipped, 355 deselected |
| 2026-08-26 | Sprint 4A External 기본 Gate | SKIPPED | GPU 5 skipped·391 deselected; Vision 1 skipped·395 deselected |
| 2026-08-26 | Sprint 4A Migration 3경로 | PASS | empty→0005, 0005→0004→0005, 0004→0005, drift 0; 임시 DB 0 |
| 2026-08-26 | Sprint 4A Final Runtime | PASS | 최신 image, Core 6개 Healthy, live/ready 200, analysis 0/0 |
| 2026-08-26 | Sprint 4A Git 인계 | PASS | `git diff --check`, Stage 0, Sprint 4A Commit·Push·PR 0, Kaputt 미추적 보존 |

## 8. 미해결 사항과 사용자 결정

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
- Sprint 2.5에서 실제 Qwen Endpoint와 `external_gpu` 5건, Backend E2E 10건을 검증했다.
  다만 합성 기준 Action Accuracy 0.23과 Missing Information F1 0.00이므로 자동 Workflow
  결정에 사용하지 않고 Policy·Human Review 경계를 유지한다.
- Sprint 3 Vision Stage는 Mock-qualified지만 실제 Vision server/model/dataset/threshold
  calibration은 검증하지 않았다. 외부 endpoint/model/sample이 없어 실제 검증은 1건 Skip이다.
- Text/Vision Alignment, Claim↔Detection matching, Policy·Routing·Review·Report·RAG는 구현하지
  않았고 Case/Evidence 접수만으로 Analysis가 자동 시작되지 않는다.
- KAPUT 참고 자료는 image-level 7-class multi-label과 item mask이며 defect bbox ground truth가
  아니다. Native→canonical mapping v1은 실제 모델 qualification 전까지 계약 가설이다.
- Vision image quality가 Provider에 없으면 `NOT_EVALUATED/null`이며 Mock quality를 실제 성능으로
  해석하지 않는다. Multi-image는 한 Stage에서 순차 처리하므로 throughput은 미측정이다.
- Sprint 2는 DLQ, 운영자 수동 재처리·취소 API, SSE, Provider 자동 선택·Fallback과 Prompt
  관리 UI를 제공하지 않는다. Raw Prompt·Provider Response를 보존하지 않는 것은 의도된
  보안·재현성 경계다.
- 실제 제품 측 결정인 결함 Taxonomy, 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는
  다음 Sprint의 ADR 대상으로 남아 있다.
- Qwen Node는 Peak VRAM 23,825 MiB로 24GB 여유가 매우 작고 FP8 KV cache를 사용한다.
  Context·동시성 변경과 실제 고객 분포 평가는 별도 requalification 대상이다.
- Community quantization의 calibration dataset은 Model Card에 기록되지 않아 제한사항이다.
- Qwen 평가 공식/enum 오류는 없었으나 100건 모두 input action `UNSPECIFIED`이고 Gold는 message
  action 추출을 요구해 Action 0.23의 의미가 모호하다. Metric bug가 아니므로 100건 재평가는
  실행하지 않았고 `QUALIFIED_WITH_LIMITATIONS`를 유지한다.
- Sprint 2는 독립 Closeout Gate를 통과했으며 승인된 로컬 Commit만 생성한다. 원격 Push와
  PR은 금지한다.
- 루트의 미추적 `kaputt_best_vision_architecture.md`는 Sprint 2와 무관한 사용자 작업물이다.
  이번 작업에서도 수정·삭제·Stage하지 않았으며 후속 소유 작업에서 별도로 다룬다.
- Sprint 4A Policy Corpus/Gold는 전부 합성 Reference이며 실제 기업 정책 정확성·법률 효력은
  검증하지 않았다. Retrieval, Embedding, BM25, pgvector, Reranker, RAG와 Policy Engine은 없다.
- v2 실제 Qwen dev/test는 endpoint를 사용하지 않아 Skip이다. Reference self-check는 모델
  평가가 아니며 향후 Prompt hash freeze 뒤 test 40건을 한 번만 실행해야 한다.

## 9. 다음 실행 항목

- [x] Sprint 1 Diff를 독립 Closeout 감사하고 로컬 기준점 Commit을 생성한다.
- [x] Sprint 2 Append-only Analysis·Outbox·LLM Vertical Slice와 최종 검증을 완료한다.
- [x] Sprint 2 Diff를 독립 감사하고 승인된 로컬 Closeout Commit만 생성한다.
- [x] 깨끗한 Sprint 2 Commit에서 `feature/sprint-2-5-qwen38-serving` 브랜치를 만든다.
- [x] 고정 Qwen3.8 Artifact Revision과 GPU/vLLM 환경의 실제 서빙 Gate를 실행한다.
- [ ] 원격 작업 전 거버넌스 PR #2 병합 또는 Sprint 1 Branch 재정렬 순서를 결정한다.
- [ ] PR #2에 유효한 사람 리뷰와 승인을 확보한다.
- [ ] GitHub Private 저장소 Branch protection을 지원하는 플랜 적용 여부를 결정한다.
- [ ] `kimhrin`에게 승인 리뷰가 가능한 권한을 부여할지, 조직 팀을 만들지 결정한다.
- [ ] 플랜·리뷰어 결정 후 Issue #1의 목표 규칙을 `main`과 `develop`에 적용한다.
- [ ] 정책에 맞는 유효 승인 또는 명시적인 Bootstrap 예외 결정 후 PR #2를 `develop`에
  병합한다.
- [x] 다섯 `external_gpu` 합성 계약을 Skip 0으로 실행하고 Model Revision을 원장에 추가한다.
- [x] Sprint 2.5 로컬 Commit은 `git log -1`로 확인하고 Push·PR 없이 인계한다.
- [ ] 실제 고객 Data 반입 전에 개인정보·Retention 승인과 Action/Missing 품질 Dataset을
  별도 설계하고 Human Review Gate를 유지한다.
- [x] Sprint 3 Vision Stage, Evidence Snapshot, Text/Vision fan-out/join과 Partial Failure를
  ADR로 고정하고 Append-only Run·Attempt·Outbox를 확장한다.
- [ ] 실제 Vision endpoint, immutable model/dataset/taxonomy/threshold와 qualification image를
  제공받으면 `make test-external-vision`으로 real model Gate를 실행한다.
- [ ] 다음 기능 Sprint에서는 먼저 Evidence Alignment 입력 계약과 Claim↔Detection matching,
  confidence calibration을 설계하고 Policy/Approval을 계속 분리한다.
- [ ] Evidence Reconciliation·Orphan Cleanup·업로드 Idempotency와 Retention 정책을
  우선순위에 따라 별도 작업으로 계획한다.
- [x] Sprint 3 Closeout Commit을 확인하고 `feature/sprint-4a-llm-reference-data`에서 LLM
  Contract v2와 합성 Reference Data를 구현한다.
- [x] Sprint 3 Closeout Commit `330cbdb`와 Sprint 4A 전용 Branch를 확인한다.
- [x] LLM Contract v2, 합성 Policy Corpus와 고정 Evaluation Dataset을 구현한다.
- [x] Sprint 4A 최종 Gate를 확정하고 미커밋 상태로 인계한다.
- [ ] Sprint 4B에서는 Policy Document/Clause DB schema와 ingestion을 먼저 만들고 BM25
  baseline→dense embedding→pgvector→metadata filter→hybrid retrieval 평가 순서로 진행한다.

## 10. 세션 종료 체크리스트

- [x] 변경한 파일과 목적을 기록했다.
- [x] 실제 실행한 검증 명령과 결과만 기록했다.
- [x] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [x] 외부 서비스 상태에 관측 날짜를 붙였다.
- [x] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [x] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [x] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [x] 아래 세션 로그를 추가했다.

## 11. 세션 로그

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

### 2026-08-26 — Sprint 2 Append-only Analysis & LLM Vertical Slice 완료

- 목표: 인증된 Reviewer/Admin의 명시적 요청을 Append-only Analysis Run으로 등록하고
  PostgreSQL Outbox·RabbitMQ·Celery를 거쳐 Strict Text Extraction Result까지 완성
- Branch: `feature/sprint-2-analysis-llm`; Sprint 2 변경은 미커밋이며 Commit·Push하지 않음
- 완료: Run·Stage·Attempt·Result·Idempotency·Outbox, Prompt/Schema Snapshot, 결정적 Mock,
  vLLM Adapter, 생성·목록·상세·Case Latest API, Dispatcher·Worker·Compose와 ADR-0009~0011
- 복구: Provider Retry/Max, Worker Lost, Soft/Hard Timeout, 활성 Lease Wake-up, Claim Token
  Fencing, 최종 Lease 만료의 원자적 Failed 종결과 Duplicate Result 방지
- 검증: Ruff, Python Format 158, Pyright 0, Fast 291, Core Integration 31, Analysis Focus
  76/13, PostgreSQL Application E2E 8, 격리 Migration 세 경로와 Drift 없음
- Live: 실제 202·Replay 200·Conflict 409·Tenant 404, Mock `SUCCEEDED`, 같은 Celery Message
  재전달 뒤 Attempt 1·Result 1, 장기 서비스 6개 Healthy
- Skip: 외부 vLLM Endpoint 미설정으로 합성 GPU 계약 5건 Skip; 외부 호출은 하지 않음
- 정리: Analysis 여섯 Table, 합성 Case·Tenant, RabbitMQ Ready/Unacked와 임시 DB가 모두 0
- Git: Commit·Push·PR 없음. 사용자 소유 미추적 Kaputt 문서는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자 Diff 검토와 별도 Git 승인 대기; 이후 별도 Sprint 3 지시가 있으면
  Vision·Alignment·Partial Failure 경계를 ADR부터 확정

### 2026-08-26 — Sprint 2 Closeout 독립 감사

- 목표: 미커밋 Sprint 2 전체 Diff를 이전 완료 보고와 독립적으로 감사하고 재현 가능한 로컬
  기준점으로 확정
- 발견: P0 0, P1 0, P2 문서 상태 2건, P3 후속 운영 경계 3건; P0/P1 미해결 0
- 검증: Ruff, Format 158, Pyright 0, Fast 291, Unit 227, Contract 45, Architecture 4,
  Integration 31, HTTP 29, 실제 PostgreSQL 세 Migration 경로와 Drift 없음
- Live: 최종 Docker Build, Core 6개 Healthy, 202·200·409·Tenant 404·`SUCCEEDED`, 같은
  Message 2회 재발행 뒤 Result 1·Attempt 1
- 정리: Analysis 여섯 Table, 합성 Tenant, RabbitMQ Ready/Unacked와 임시 DB가 모두 0
- Git: 승인된 Sprint 2 범위만 로컬 Commit하고 Push·PR 금지; Kaputt 사용자 파일은
  수정·삭제·Stage하지 않음
- 다음 작업: 깨끗한 Commit에서 Sprint 2.5 브랜치를 만들고 고정 Qwen3.8 실제 서빙 검증

### 2026-08-26 — Sprint 2.5 Qwen3.8 실제 서빙 Qualification

- 목표: 고정 `cyankiwi/Qwen3.8-27B-AWQ-INT4` revision을 단일 RTX 4090에서 private,
  text-only, non-thinking strict extraction으로 실제 검증
- 환경: vLLM 0.26.0 image digest, Transformers 5.14.1, CUDA 13.0, Driver 580.173.02,
  max length 8192, sequence 1, FP8 KV, eager, CPU Offload 없음
- 보안: private Tailscale bind와 인증. Process audit에서 초기 CLI API Key 노출을 발견해
  일회용 Key를 즉시 회전하고 `VLLM_API_KEY` 환경변수 주입으로 수정·재검증
- 재현성: `/v1/models` 일치, Cold Start 2회, cache-hit API Ready 97초, 26m19s 동안
  Restart·OOM·Error 0
- 품질: Prompt 1.0.0의 중복 Enum 2건을 숨기지 않고 재현. vLLM이 `uniqueItems`를 거부함을
  확인한 뒤 Taxonomy·set 지시의 Prompt 1.0.1로 version bump; 100건 안전 Gate 전부 통과
- 제한: Issue F1 0.95이나 Action Accuracy 0.23, Missing F1 0.00. Spot-check 안전 20/20,
  Issue 19/20, Action 10/20, Missing 8/20이라 Human Review 필수
- 성능: Profile A p50/p95 1.470/1.558초, TTFT 0.089/0.176초, 36.36 token/s;
  Peak VRAM 23,825 MiB. 동시성 2는 안정적이지만 latency가 약 2배
- Integration: 실제 External 5/5, Backend E2E 성공 10/10, Result·Attempt 각 10,
  Duplicate No-op 1/1, Timeout Retry 2 Attempt, Raw Column·unsafe Outbox 0
- 정리: 합성 Case/Run 22와 관련 Row 정리, Queue·Orphan 0, Core 6개 기본 Mock Healthy
- 검증: Ruff, Format 162, Pyright 0, Fast 291, Core Integration 31, 실제 External 5
- 판정: `QUALIFIED_WITH_LIMITATIONS`; Push·PR 없음. 다음 작업은 로컬 Commit SHA 기록과
  Sprint 3 Vision 계약 준비

### 2026-08-26 — Sprint 3 Vision Analysis와 Multimodal Fan-out/Join

- 목표: 기존 Append-only Analysis에 image별 Vision Stage/Result, immutable Evidence Snapshot,
  Text/Vision 독립 fan-out과 terminal join을 추가
- Branch/Base: `feature/sprint-3-vision-analysis` / `7d63cbb`; Commit·Push·PR 없음
- 완료: canonical schema/quality/bbox, KAPUT native mapping, 10 Mock scenario, Remote multipart
  Adapter, `20260826_0004`, Snapshot/Result/Detection repository, API detail과 no-image 422
- Workflow: text-only 유지, multimodal 2 Stage/Event, multi-image 순차 append, retry/lease/fencing,
  `SUCCEEDED`/`PARTIAL_SUCCESS`/`FAILED` 집계와 partial result 보존
- 발견·수정: 병렬 Worker가 동시에 Run `QUEUED→RUNNING` CAS를 시도할 때 패한 Stage claim이
  rollback되어 고립되던 결함. Run이 이미 `RUNNING`이면 claim을 유지하도록 양 Stage 수정
- LLM 감사: taxonomy/metric 수식 오류 0, Missing set/empty convention 정상. Action input/gold
  의미 모호성을 확인하고 exact/macro/support diagnostics와 regression test 추가; 재평가 미실행
- 검증: Ruff, Format 167, Pyright 0, Fast 328, Integration 36, Architecture/Contract/E2E 55,
  isolated Migration lifecycle/drift, 실제 MinIO bounded read, Docker 6개 Healthy와 Queue 0
- Live: Login→PNG upload→text-only success→multimodal success(2 Stage, Result/Detection 1),
  no-image 422, Text success/Vision failure partial success; 합성 Case 5/Object 4 정리
- External Vision: endpoint/model/sample 미제공으로 1 skipped·369 deselected,
  `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`; 판정 `MOCK_QUALIFIED`
- 문서: ADR-0013~0017, 설계 03~10, README, Sprint 3 Progress와 현재 상태 동기화
- 다음 작업: 실제 Vision qualification 자산 확보 또는 별도 Sprint에서 Evidence Alignment 입력
  계약과 Claim↔Detection matching/calibration을 먼저 설계

### 2026-08-26 — Sprint 3 Closeout 감사

- 목표: 미커밋 Sprint 3 전체 Diff를 코드·테스트·Migration·Runtime 기준으로 재감사하고 로컬
  기준점 Commit 조건을 확정
- 감사: Evidence Snapshot, append-only Vision Result/Detection, 독립 fan-out, CAS 경쟁 수정,
  DB 기반 join, 네 partial 조합, 6-ID Queue, tenant 복합 FK와 canonical geometry 확인
- 검증: Ruff, Format 165, Pyright 0, Fast 328, Unit 264, Contract 45, Architecture 4, E2E 6,
  Core Integration 36, 격리 Migration 세 경로와 drift 0
- Runtime: API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6개 Healthy, HTTP ready,
  RabbitMQ analysis queue ready/unacked 0
- Skip: 실제 Vision 자산 미제공으로 외부 Vision 1건 `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`
- 판정: P0 0, P1 0, `SPRINT_3_CLOSEOUT=PASS`; Push·PR 금지, Kaputt 사용자 파일 제외
- 다음 작업: 승인된 Sprint 3 범위만 로컬 Commit한 뒤 Sprint 4A 전용 브랜치를 생성

### 2026-08-26 — Sprint 4A LLM Contract v2와 Reference Data

- 목표: LLM 출력 의미를 v2로 분리하고 Policy Retrieval/RAG 구현 전에 합성 Reference Corpus와
  고정 Gold/평가 기준을 구축
- Git: Sprint 3 Closeout `330cbdb`에서 `feature/sprint-4a-llm-reference-data` 생성;
  Sprint 4A Commit·Push·PR 없음, Kaputt 사용자 파일 제외
- LLM: v1 보존, Pipeline/Prompt/Schema v2, 복수 action exact quote, text ambiguity,
  deterministic completeness/action consistency와 append-only v2 child/API
- Reference: 합성 Tenant 2, Document 24, Clause 168, Policy Type 9, retired 6,
  Exception/Evidence Requirement 각 48, duplicate 0
- Evaluation: Extraction 160, Retrieval 120, Grounding 50, Injection 30, Demo 10;
  manifest/hash/report와 Gold missing/cross-tenant 0
- Live: Docker image rebuild 후 Migration `0005`/drift 0, v2 Mock SUCCEEDED/action 2/
  MULTIPLE_EXTRACTED/rule 1.0.0; 합성 row와 queue 정리
- Skip: 실제 Qwen endpoint를 사용하지 않아 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Gold
  self-check를 모델 평가로 표현하지 않음
- 범위 밖: Embedding, BM25, pgvector, hybrid/reranker, RAG API, Policy Engine, Alignment,
  Routing, Review, Report, Vision 변경
- 다음 작업: 최종 전체 Gate 수치를 확정하고 Sprint 4B의 DB ingestion/검색 baseline에 인계

### 2026-08-26 — Sprint 4A 최종 Gate와 세션 인계

- 목표: Sprint 4A 미커밋 Diff를 정적 검사, 전체 회귀, 데이터 결정성, Migration 3경로와
  최신 Docker Runtime으로 최종 검증하고 다음 에이전트가 바로 이어갈 수 있게 확정
- 보강: Corpus validator가 순환 Parent, 문서–Clause 메타데이터 불일치, 만료 ACTIVE,
  비대칭·Cross-Tenant Supersession을 fail-closed하도록 강화하고 Contract 5건 추가
- 검증: Ruff, Format 179, Pyright 0, Fast 354/42 deselected, Unit 294, Architecture 4,
  Contract 50, E2E 6, Core Integration 36/외부 GPU 5 skipped
- 데이터: Policy 24/168과 Evaluation 160/120/50/30/10 재생성·검증, 반복 Build aggregate
  hash 동일, broken/duplicate/cross-tenant 0
- Migration/Runtime: empty→0005, 0005→0004→0005, 0004→0005, drift 0, 임시 DB 0;
  최신 image Core 6개 Healthy, live/ready 200, analysis queue 0/0
- Skip: Sprint 4A 실제 Qwen은 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Vision도 기존 실제 자산
  미제공으로 1건 Skip. Gold self-check는 실제 모델 평가가 아님
- Git: Branch `feature/sprint-4a-llm-reference-data`, Base `330cbdb`; Sprint 4A Commit·Push·PR
  없음. `kaputt_best_vision_architecture.md`는 사용자 파일로 미수정·미Stage
- 판정: `REFERENCE_DATA_QUALIFIED_WITH_LIMITATIONS`
- 다음 작업: 별도 Sprint 4B 지시에서 Policy Document/Clause DB schema와 ingestion부터 시작하고
  BM25 baseline→dense embedding→pgvector→metadata filter→hybrid retrieval 평가 순서 유지

### 2026-08-26 — Sprint 4A 독립 Closeout 감사

- 목표: Sprint 4A 전체 Diff를 코드·데이터·Migration·Runtime 기준으로 독립 재감사하고 승인된
  로컬 기준점 Commit 조건을 확정
- 감사: v1 호환, v2 append-only child/API, 합성 Corpus tenant/version/parent 무결성과 고정
  Gold 참조를 확인; P0 0, P1 0
- 검증: Ruff, Format 179, Pyright 0, Fast 354/42 deselected, Unit 294, Architecture 4,
  Contract 50, E2E 6
- Integration: 장기 실행 실제 Dispatcher가 테스트 Outbox를 선점해 최초 1건 실패; 실행
  서비스를 격리한 재실행은 36 passed, 외부 GPU 5 skipped
- 데이터: Policy 24/168/2와 Evaluation 160/120/50/30/10 재생성, stable aggregate hash,
  broken/duplicate/cross-tenant 0
- Migration/Runtime: 세 경로·drift 0, 임시 DB cleanup, 최신 Core 6개 Healthy,
  live/ready 200, queue 0/0
- 판정: `SPRINT_4A_CLOSEOUT=PASS`; 정확한 Commit message는
  `feat: add LLM contract v2 and policy reference corpus`, Push·PR 금지
- 안전: `kaputt_best_vision_architecture.md`는 사용자 파일로 계속 미수정·미Stage
- 다음 작업: 승인 범위만 Stage/Commit하고 해당 SHA에서
  `feature/sprint-4b-policy-retrieval`을 생성
