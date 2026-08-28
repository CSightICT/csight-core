# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 구현 증거는 `SPRINT_0_FOUNDATION.md`와
`SPRINT_1_CASE_EVIDENCE.md`, 독립 감사 증거는 `SPRINT_1_CLOSEOUT.md`, 현재 분석 경로는
`SPRINT_2_ANALYSIS_LLM.md`, 독립 감사 원장 `SPRINT_2_CLOSEOUT.md`, 실제 모델 기록
`SPRINT_2_5_QWEN38_SERVING.md`, `SPRINT_3_VISION_ANALYSIS.md`, 최신 구현 원장
`SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`와 합성 시나리오 검증 계약
`SCENARIO_POC_ACCEPTANCE_RUNNER.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 5C 내부 데모 PASS; 실제 E3 Runtime·현실형 가상 문의/Commerce Context·사람 확정형 빠른 검토·환불 확인서·자연어 업무 UI·고객 안내 메일 시뮬레이션·tenant 비식별 데이터 자산 원장 종합 회귀 PASS |
| 진행 중 작업 | 기존 10건을 보존한 `poc_closed_set/2.0.0` 확장 팩 10건을 추가해 현재 시연 범위를 결함 후보 12·사람 확인 저점수 참고 8의 총 20건으로 늘렸다. 상품군 4/4·결함군 3/3을 표현하지만 클래스별 성능평가가 아니다. 다음은 인증 상담원 검토와 20건 연속 운영 측정이다. |
| 마지막 갱신일 | 2026-08-28, Asia/Seoul |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | `CSightICT/csight-core` — Private. 누적 운영형 상담원 제품과 방향 전환 기록을 새 `origin/codex/operator-console-product-direction`에 기능 기준점 `c90357d`로 백업; PR·`develop/main` 병합 없음 |
| 로컬 Git | `codex/operator-console-product-direction`; `feature/scenario-poc-hard-plastic`의 `dfaa373`에서 분기. 기능 기준점 `c90357d`를 원격 확인했고 이 원장 갱신은 후속 문서 커밋으로 기록. 사용자 소유 미추적 문서 3개 보존 |
| 마지막 검증 관측 | 2026-08-28 22:29 KST, 상담·검토·지표·보고서·메일 화면에서 `PoC/모의/시뮬레이션/DRY-RUN/Mock/데모/시연` 개발 문구를 운영형 표현으로 교체. 기존 기록은 표시 단계에서 정리하고 신규 메일 본문도 같은 계약을 적용. 외부 결제·메일 시스템 미반영 문구와 실행 차단은 유지. Web lint·typecheck·OpenAPI sync·24 files/63 tests·build PASS, 관련 Backend 15 tests와 Ruff·Format PASS. local/public JS `index-BdA6eGFX.js`, CSS `index-CWAdx66O.css` 일치, Core 7개 서비스 healthy. |
| 마지막 GitHub 관측 | 2026-08-28 22:39 KST, 새 원격 브랜치 `origin/codex/operator-console-product-direction` 생성과 기능 커밋 `c90357da845a522bd3ce8ba8446c39f57139fafe` 일치 확인. PR·`develop/main` 병합 없음 |

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
| Sprint 3 실제 Vision | INTERNAL_E3_CONNECTED_WITH_LIMITATIONS | SHA 고정 E3를 loopback MPS endpoint와 Core에 연결; 합성 이미지 1건이며 제품 qualification 아님 |
| Sprint 4A LLM Contract v2 | PASS | v1 보존, v2 Prompt/Schema/Persistence/API와 live Mock 통과 |
| Sprint 4A Policy Reference | PASS | 합성 2 Tenant, 24 Document, 168 Clause, retired 6 |
| Sprint 4A Evaluation Data | PASS | 160/120/50/30/10, Gold missing·cross-tenant 0 |
| Sprint 4A 실제 Qwen 평가 | SKIPPED | Endpoint 미사용; `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| Sprint 4A 독립 Closeout | PASS | P0/P1 0, 정적·전체 회귀·데이터·Migration·Docker 재검증 |
| Sprint 4A 로컬 Commit | PASS | `6f3a667 feat: add LLM contract v2 and policy reference corpus`, Push·PR 없음 |
| Sprint 4B Corpus Ingestion | PASS | Tenant 2, Document 24, Clause 168, idempotent reuse, conflict 차단 |
| Sprint 4B Lexical/Dense/Hybrid | QUALIFIED_WITH_LIMITATIONS | Exact BM25, Qwen 1024-d exact cosine, weighted RRF; 합성 corpus 한계 |
| Sprint 4B Retrieval API | PASS | Principal tenant, 세 mode, metadata 선필터, provider-down 격리 |
| Sprint 4B Locked Evaluation | PASS | Dev 80 freeze, Test 40 한 번, correctness 위반 0 |
| Sprint 4B 독립 Closeout | PASS | P0/P1 0, 전체 회귀·실제 MPS·Migration·Docker 재통과 |
| Sprint 4B 로컬 Commit | PASS | `4216028 feat: add hybrid policy retrieval baseline`, Push·PR 없음 |
| Sprint 4C-1 Candidate Upper Bound | PASS | Dev로 K20/final10 선택, Test 진단 한 번, candidate recall 상한 0.9375 |
| Sprint 4C-1 Qwen Reranker | QUALIFIED_WITH_LIMITATIONS | 고정 revision, MPS 실서빙, concurrency 1; CPU·실사용 분포 미검증 |
| Sprint 4C-1 Reranked API | PASS | `HYBRID_RERANKED`, 두 tenant smoke, no fallback, provider-down 503 |
| Sprint 4C-1 Locked Evaluation | NO_MEASURABLE_GAIN | Test Recall 동일, MRR 0.53833→0.51250, nDCG 0.59841→0.59802 |
| Sprint 4C-1 Profile Persistence | PASS | Migration `0007`, reranker profile 1, ACTIVE execution profile 2 |
| Sprint 4C-1 독립 Closeout | PASS | P0/P1 0, 전체 회귀·외부 모델·Migration·Docker 재통과 |
| Sprint 4C-1 로컬 Commit | PASS | `14cae29 chore: qualify qwen3 policy reranker`, Push·PR 없음 |
| Sprint 4C-2 Holdout | PASS | 독립 Dev 80/Test 40, sealed, broken/cross-tenant 0, stable hash |
| Sprint 4C-2 Query Plan/API | PASS | Strict 1~3 query, append-only Run/Outbox/Query/Hit, POST/List/Get |
| Sprint 4C-2 LLM 실제 평가 | SKIPPED | `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Mock 성능 미보고 |
| Sprint 4C-2 Locked Evaluation | BLOCKED_EXTERNAL_LLM | RAW가 deterministic보다 우수; 실제 LLM 미평가 |
| Sprint 4C-2 로컬 Commit | PASS | `feat: add case-based policy retrieval query planning`; Push·PR 없음 |
| Sprint 4C-3A Citation Pack | PASS | clause/version/source/query provenance immutable snapshot |
| Sprint 4C-3A Structural Guardrails | PASS | Grounding 50 + Injection 30, 위반 0, replay 100% |
| Sprint 4C-3A Async Runtime | PASS | PostgreSQL/RabbitMQ/Celery Mock, replay 200, tenant 404, provider-down no fallback |
| Sprint 4C-3A Semantic Grounding | SKIPPED | 실제 Qwen 부재; precision/recall/faithfulness 미주장 |
| Sprint 4C-3A 독립 Closeout | PASS | P0 0, P1 0, 전체 회귀·Migration·최신 Docker·Live Gate 통과 |
| Sprint 4C-3B Local MLX PoC | QUALIFIED_WITH_LIMITATIONS | Local extraction/query/grounding, RAW 유지, top-3 context, 실제 timeout fault 미실행 |
| Sprint 4C-3B 독립 Closeout·Commit | PASS | P0/P1 0, `d0950f6 feat: add local MLX LLM grounding PoC`, Push·PR 없음 |
| Sprint 5A Typed Policy Engine | PASS | registry/rule/effect/qualification/append-only runtime 및 전체 검증 완료 |
| Sprint 5A Synthetic Rule Set | PASS | Tenant 2, Rule Set 2, Rule 24, Source link 24, forbidden effect 0 |
| Sprint 5A Dev/Test Evaluation | PASS | Dev80 freeze, sealed Test40 1회; exact/condition/effect/source/version/replay 100% |
| Sprint 5A Migration·Live | PASS | 세 lifecycle 경로 drift 0, Core 6 healthy, async smoke와 tenant 격리 통과 |
| Sprint 5B Task·Packet·Audit | PASS | effect mapping 1.0.0, task/packet/CREATED 각 1, duplicate event NOOP |
| Sprint 5B Assignment·State | PASS | CAS claim, concurrent 1 success/1 conflict, release/evidence/resume/escalate |
| Sprint 5B Human Decision | PASS | authenticated human-only resolve, rationale/basis 검증, immutable decision 1개 |
| Sprint 5B Authorization | PASS | Viewer read-only, Manager/Safety Admin-only, assignee/Admin 및 tenant 격리 |
| Sprint 5B Dev/Test Evaluation | PASS | Dev60/Test30 sealed; workflow metrics 1.0, safety violation 0 |
| Sprint 5B Async Reliability | PASS | 4 outbox claim/lease/backoff/terminal state, 3 worker lease/fencing, hash fail-closed |
| Sprint 5B Migration·Live | PASS | `0012` 세 lifecycle/drift 0, Core 6 healthy, broker outage recovery·live smoke |
| Sprint 5B Git Handoff | PASS | `4aefae6 feat: add human review workflow`, 원격 5B 기능 브랜치 백업 완료; PR 없음 |
| Sprint 5C Resolution·Action Contract | PASS | Case와 분리된 projection/event, mapping 1.0.0, explicit input only, immutable Intent |
| Sprint 5C DRY-RUN Reliability | PASS | 두 durable outbox, worker fencing, deterministic network-free simulation, `LIVE` fail-closed |
| Sprint 5C Report·KPI | PASS | content-hashed `review_report/1.0.0`, tenant KPI numerator/denominator/sample count |
| Sprint 5C Customer Communication | PASS_WITH_SCOPE | immutable EMAIL simulation v1.1, 실제 SMTP/통지 0, `side_effects_performed=false`; terminal Report 필요 |
| Sprint 5C Tenant Data Asset | PASS_WITH_SCOPE | terminal Report와 같은 transaction에서 PII 원문 제외 append-only asset 자동 적재; 30/60건 기준선 Gate |
| Sprint 5C React Console | PASS | OpenAPI 기반 상담원 화면과 5개 fixture-driven Playwright 시나리오; 3–5는 live causal E2E 아님 |
| Sprint 5C Migration·Live | PASS | Head `0016`, 기존 Report backfill, drift 0, Core runtime healthy, Remote E3 설정 보존 |
| Sprint 5C Git Handoff | PASS | `0a5f529 feat: add case resolution and PoC console`, 원격 5C 기능 브랜치 백업 완료; PR 없음 |
| HDP-100 합성 Scenario Pack | OFFLINE_READY | fictional product, 36 synthetic Case/Gold, 10 clause/7 rule, 5 demo, acceptance 9/9 |
| E3 보고서 지표 | REPORTED_NOT_REPRODUCED | AP 0.884863, AUROC 0.931604, threshold 0.8984375는 담당자 보고 수치; CSight 재현 아님 |
| Binary Vision Runtime | ACTUAL_E3_INTERNAL | image-level any-defect E3 score와 threshold 해석을 실제 checkpoint로 live 연결; Mock 기본값은 회귀용으로 유지 |
| 실제 E3 Runtime | PASS_WITH_SCOPE | exact E3 SHA/size/schema, offline strict load, loopback HTTP, MPS forward와 Core append-only 저장 통과; 합성 연결 증거만 해당 |
| E3 Top-100 Positive Replay | PASS_WITH_SCOPE | selected-correct defect 100/normal 0 전수 forward와 hard-plastic Core 6건 통과; 연결 재현 증거이며 성능평가·제품 qualification 아님 |
| Kaputt Qwen VLM Offline Enrichment | BLOCKED | Query Crop+동일 상품 Reference Crop+비교 Prompt 4/4 기술 성공·민감 패턴 0; 상품 유형 1/4·defect-positive 0/2로 전체 Batch 품질 Gate FAIL, 공식 Label/E3 대체 금지 |
| Kaputt Qwen Product Metadata 30 | BLOCKED | 분리 schema로 30/30 성공·specific generic name 25·uncertain 5·금지/민감 필드 0. taxonomy 공백과 Human Gold 부재로 자동 Catalog 적용 전 사람 검수 필요 |
| Vision Assessment Migration | PASS | DB Head `0015`, migration lifecycle·drift와 append-only assessment persistence 통과 |
| Parallel Text/Vision Join | PASS | parent `FOR UPDATE` 직렬화와 terminal redelivery reconciliation; 새 live Run과 기존 orphan 복구 통과 |
| HDP-100 Git Handoff | PASS | 기능 `dfd6db2`, closeout `5c152fd`; local HEAD와 동일 원격 기능 브랜치 SHA 확인, PR·`develop` 병합 미실행 |
| R1 Visual-Aligned Inquiry Demo | PASS | 이미지 관찰과 고객 진술을 분리한 4~5문장 가상 문의 10건; 결함 후보 6·기준 미만 참고 4, seed/replay와 private Evidence SHA 검증 |
| R1 Fictional Product Catalog | PASS | 검증된 사진 10장에 표시 전용 가상 상품명·SKU·KRW 가격대·문의 목적을 매핑; 목록 검색/표시와 상세 상품 카드 적용, 실제 판매가·환불 입력 추론 0 |
| R2 Synthetic Commerce Context | PASS | `synthetic_commerce_context/1.0.0` 고객·주문·결제·배송 스냅샷 10건 DB 저장; 연락처/결제/운송장 마스킹, 가상 주소 표시, 환불 2건 결제금액=명시 환불액, Action 추론 0 |
| R3 Closed-set Demo Expansion | PASS_WITH_SCOPE | 기존 10건을 변경하지 않고 10건 추가, 최신 시연 팩 20건=결함 후보 12+사람 확인 저점수 참고 8. 실제 E3 성공·재실행 멱등성·Private Evidence integrity 통과, 상품군 4/4 표현. 성능평가·정상 확정·실제 Action 아님 |
| Korean Business-language Console | PASS_WITH_SCOPE | 문의 목록·상세·검토 대기함·검토 상세를 한글 상품명 우선으로 표시하고 현재 DB 상품 참조 49종에 표시 전용 이름 적용. 요청 유형·검토 유형·우선순위·페이지 제목·모의 처리 문구도 한글화. 식별용 주문/SKU와 API 값은 보존, 인증 화면 수동 육안 확인은 미실행 |
| Review Decision Workspace Readability | PASS_WITH_SCOPE | 허용/비허용 상세 화면을 최대 1540px, 결정 패널 460px 이상, 선택 버튼 90px로 확대하고 데스크톱 밀도·태블릿 한 열·모바일 보정을 적용. 인증 브라우저 육안 확인은 미실행 |
| Operator-friendly Policy Summary | PASS_WITH_SCOPE | 원본 정책 enum·qualification JSON·모델 식별자를 첫 화면에서 제거하고 정책 권고, 문의/이미지 분석, 일치 확인, 근거 정합성을 자연어 상태로 표시. 원본 API/DB snapshot은 불변 보존 |
| Operational-language Console | PASS_WITH_SCOPE | 화면과 출력 문서의 개발·검증 용어를 상담 업무 표현으로 교체하고 기존 `DEMO` 식별자·주소는 표시 단계에서 정리. 외부 결제·메일 시스템 미연결과 실제 처리 0 경계는 명시적으로 유지. 인증 화면 수동 육안 확인은 미실행 |
| Product Direction Rationale | PASS | 모델 중심 기술 검증에서 사람 확정형 상담 운영 제품으로 이동한 근거, 채택 원칙, 의도적 제외 범위와 실제 고객 승격 조건을 `docs/product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`에 기록 |
| Operator Workflow Git Handoff | PASS | 누적 변경 100개 파일을 `c90357d`로 커밋해 새 원격 브랜치에 Push. 고신뢰 Secret·1 MiB 초과 staged blob 0, 사용자 소유 문서 3개 제외, PR 없음 |
| R1 Three-Column Console | PASS | 문의 내용·이미지 근거·정책 기반 권고 3열, legacy v2 숨김·R1 fail-closed 표시, 하단 운영 상세 접기 |
| R1 Consultant Workspace Simplification | PASS | `지금 할 일` 단일 CTA·4단계 진행 표시·문의/이미지+정책 2열 본문·기술 정보 접기, 데스크톱 inert X 제거 |
| R1 Continue Policy-Date Recovery | PASS | 업무 시간대 `Asia/Seoul` 기준일 계산으로 UTC/KST 효력일 422 해소; API `{error}` 계약의 코드·메시지를 UI에 그대로 표시 |
| R1 Human-confirmed Quick Review | PASS | PoC 준비도 0.70 Gate, 정책 효과 기반 단일 허용 mapping·비허용 `REJECT_REQUEST`, 자동 basis/rationale, CAS Claim→Resolve→비동기 Report 자동 열기; 모델 자동 Decision 0 |
| R1 Refund Processing Confirmation | PASS | immutable report snapshot만 사용한 환불 전용 운영 문서·A4 인쇄 화면; 금액/통화 누락 fail-closed, 결제취소·고객통지·RMA 미연동 표시, 실제 환불 완료 주장 0 |
| CSight Commerce Fictional Policy | PASS | 신규 8 Document·52 Clause, 전체 20/136; 문서·Index `2.0.0`, canonical Rule Set `2.0.1` sole active |
| R1 Policy→Human Review | PASS | 수리·Safety·단순변심 3건이 Policy `SUCCEEDED`, matching Review `PENDING`; Decision·Resolution·Action 0 |
| R1 Public Sharing Gate | BLOCKED | Cloudflare Access·강한 Credential·이미지 재배포 권리 미확보; 현재 본인 내부 시연 전용 |
| Limited PoC 승격 | BLOCKED | 실제 기업 Data/Policy는 오늘 범위에서 의도적으로 제외; Privacy·제품도메인 Vision·Shadow·Qwen 증거 미확보 |
| GitHub 협업 문서·템플릿 | PASS | 브랜치 규칙, PR·Issue 템플릿, CODEOWNERS 작성 |
| GitHub PoC·MVP·Release Branch Audit | PASS | 현재 PoC=`feature/scenario-poc-hard-plastic`; MVP 통합 기준=`develop`; 최종 릴리스 기준=`main`. 별도 `poc/mvp/final` branch·tag 없음, PoC 최신화 후에도 역할 유지 |
| PoC 안전 원격 백업 | PASS | Secret·5 MiB 초과·가중치·원본 이미지 0. E3/backend `0f4de4b`, Web `b3e09cf`, handoff `81b6e20`을 fast-forward Push했고 CI #108 PASS; 사용자 소유 문서 3개 미추적 보존 |
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

## 5.4. Sprint 4B 완료 체크리스트

- [x] Sprint 4A 독립 Closeout 후 정확한 로컬 Commit `6f3a667` 생성
- [x] `feature/sprint-4b-policy-retrieval` Branch 생성, Closeout 후 로컬 Commit 승인, Push·PR 없음
- [x] `20260826_0006`과 ingestion/document/clause/profile/embedding/index 6개 table
- [x] Normalized JSONL/manifest 기반 ingestion, 24 document/168 clause, 반복 run 재사용
- [x] 동일 document version의 다른 content hash를 명시적 mismatch로 차단
- [x] Principal tenant, ACTIVE, effective interval과 allowlisted metadata 선필터
- [x] Exact BM25와 versioned Korean tokenizer; dev k1 1.2/b 0.75 freeze
- [x] Qwen3-Embedding-0.6B pinned revision, 실제 1024-d MPS embedding 168개
- [x] pgvector exact cosine similarity와 NaN/Inf/dimension 검증
- [x] Versioned weighted RRF k20/lexical1.5/dense0.5, dedupe/stable tie
- [x] Read-only LEXICAL/DENSE/HYBRID API; decision/tenant/vector/internal ID 미노출
- [x] Provider down에서 lexical 200, dense/hybrid 503, Core ready 200
- [x] Dev 80에서 profile 선택 후 Test 40 한 번 실행; 이후 재튜닝/재평가 없음
- [x] Cross-tenant/future/retired/wrong-version/hard-negative/duplicate 0, determinism 100%
- [x] Qwen host-native qualification, external embedding Skip 0
- [x] ADR-0026~0038, RAG guide 4개, model manifest, 설계 03~10, README 갱신
- [x] 사용자 `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage

## 5.5. Sprint 4C-1 완료 체크리스트

- [x] Sprint 4B를 `4216028`로 로컬 Commit하고 전용 Branch 생성; Push·PR 없음
- [x] Frozen HYBRID_RRF 후보 K 10/20/30/50와 oracle 상한을 Dev에서 측정
- [x] Dev만으로 candidate K 20, final K 10 선택; Test 후보 진단은 한 번만 실행
- [x] Qwen3-Reranker-0.6B artifact revision, serialization, score 의미와 runtime 고정
- [x] Host-native MPS private service와 health/models/rerank endpoint 실제 검증
- [x] Pair token 길이·truncation, cold/warm latency, K별 latency와 concurrency 측정
- [x] Technology-neutral Port/Profile과 Remote·Mock Adapter, complete-set 검증
- [x] 기존 세 mode 불변의 `HYBRID_RERANKED`, no fallback, provider-down 503
- [x] Migration `20260826_0007`, immutable reranker/execution profile과 tenant resolution
- [x] Dev 80 freeze 후 locked Test 40 한 번; Test 결과로 profile 재조정하지 않음
- [x] Correctness 위반과 candidate mutation 0, Dev deterministic rerun 100%
- [x] 실제 두 tenant reranked smoke와 기존 mode/provider-down 회귀
- [x] ADR-0039~0048, architecture/evaluation guide, manifest, progress, README 동기화
- [x] Ruff·Format·Pyright·Fast·대상별·Integration·External·Migration·Runtime Gate 통과
- [x] `RERANKER_NO_MEASURABLE_GAIN`을 숨기지 않고 Sprint 4C-2 입력으로 보존
- [x] Sprint 4C-1 Commit·Stage·Push·PR 없음, Kaputt 파일 미수정·미삭제·미Stage

## 5.6. Sprint 4C-3A 완료 체크리스트

- [x] Sprint 4C-2를 `a282817` 로컬 Commit으로 고정하고 전용 Branch 생성
- [x] 성공 Retrieval Run에서 immutable content-hashed Citation Pack 생성
- [x] rank, clause/document version, source/effective/query/retrieval provenance snapshot
- [x] 고정 중립 summary, 문장별 citation 필수, decision-free strict output schema
- [x] Citation allowlist, duplicate normalization, tenant/version/effective-date fail-closed 검증
- [x] Append-only profile/pack/item/run/result/outbox Migration `20260827_0009`
- [x] Identifier-only Queue, thin Celery Worker, no silent fallback
- [x] Case 하위 POST/List/Get, Principal tenant scope, Viewer read-only
- [x] Mock orchestration과 vLLM strict JSON/citation contract 테스트
- [x] Grounding 50 + Prompt Injection 30 구조 평가, 위반 0, replay 100%
- [x] Semantic citation/unsupported claim/faithfulness를 실제 Qwen 부재로 SKIPPED
- [x] ADR-0059~0064, RAG architecture/evaluation guide, manifest, progress 동기화
- [x] 독립 Closeout에서 P0/P1 미해결 0, 최신 Docker Build·Live Runtime 재통과
- [ ] 실제 Qwen 4C-3B Dev qualification → freeze → sealed Test
- [ ] Sprint 5 versioned Policy Engine + Human Review 연결

## 5.7. Sprint 5A 진행 체크리스트

- [x] Sprint 4C-3B를 `d0950f6 feat: add local MLX LLM grounding PoC`로 로컬 Commit
- [x] `feature/sprint-5a-policy-engine-core` 브랜치 생성; Push·PR 없음
- [x] Typed field/operator registry와 missing/qualification semantics 구현
- [x] Final decision을 표현할 수 없는 effect allowlist와 human-review gate
- [x] Synthetic tenant 2, rule set 2, rule/source link 24/24 build·validation·DB ingestion
- [x] Source clause same-tenant/version/hash/effective interval 검증과 immutable version conflict 차단
- [x] Migration `20260827_0010_policy_engine`, rule/runtime/outbox 10개 table과 drift 0
- [x] Frozen typed input/qualification snapshot, 고객 원문·grounding text 비복제
- [x] POST 202/replay 200/List/Get와 identifier-only outbox/RabbitMQ/Celery route
- [x] Pure deterministic engine, append-only result, duplicate task `NOOP`
- [x] Dev80 freeze 후 sealed Test40 단 1회; rerun guard와 artifact verifier
- [x] ADR-0065~0076, Policy 문서 4개, README/설계/Makefile 동기화
- [x] 전체 Ruff/Format/Pyright/default/integration/migration lifecycle 최종 실행
- [x] 최신 Docker image rebuild, 5 queues consumer, API live smoke 및 cross-tenant/duplicate 검증
- [x] 최종 실제 수치를 Sprint 5A 문서와 아래 session log에 append

## 5.8. Sprint 5B 완료 체크리스트

- [x] Sprint 5A 독립 감사 후 `67eafdd feat: add versioned policy engine core` 로컬 Commit
- [x] `feature/sprint-5b-human-review-workflow` 생성; `4aefae6` Commit과 동일 원격 기능 브랜치 백업, PR 없음
- [x] Policy effect 집계와 `review_task_mapping/1.0.0` task type/priority 결정
- [x] 성공 Policy Evaluation과 `human_review.requested.v1` durable event 원자 저장
- [x] identifier-only `human-review` queue, bounded retry, thin task-creation worker
- [x] Task/Packet/CREATED action 원자 생성과 duplicate event/task NOOP
- [x] allowlisted metadata·qualification·policy/analysis provenance immutable packet/hash
- [x] PENDING/CLAIMED/WAITING/ESCALATED/RESOLVED typed state machine
- [x] CAS/row-lock claim, current assignment unique, concurrent claim 1 success/1 conflict
- [x] Release, evidence request, Admin/new-evidence resume, escalation과 assignment history
- [x] Viewer read-only, reviewer assignee scope, Manager/Safety/Escalated Admin-only
- [x] 명시적 human Resolve만 Decision/Basis/RESOLVED action/projection 원자 생성
- [x] Rationale 10–2000, policy basis 필수, citation/rule/evidence/run/tenant fail-closed
- [x] deterministic outcome relation 1.0.0과 task당 immutable Decision 1개
- [x] Queue/List/Detail/Case list와 여섯 action API, raw model/audit payload 비노출
- [x] Migration `20260827_0011_human_review` 7개 table, 세 lifecycle, drift 0
- [x] Human Review evaluation Dev60 freeze 후 sealed Test30 단 1회, verifier PASS
- [x] ADR-0077~0088, Review 문서 5개, README/설계/Make/환경 문서 동기화
- [x] Ruff, Format, Pyright, 전체 default/integration, Docker/queue/live smoke 검증
- [x] Migration `20260827_0012_async_reliability`, 네 Outbox claim/lease/backoff/terminal state
- [x] Retrieval·Grounding·Policy worker lease/fencing과 permanent/retry-exhausted 실패 기록
- [x] Packet·Decision hash 조회/Resolve 직전 재검증과 변조 fail-closed
- [x] Integration 임시 DB 격리·실행 후 삭제·잔존 0 검증
- [x] 실제 RabbitMQ 중단→backoff→복구와 duplicate delivery `NOOP` 검증
- [x] 외부 환불·교환·결제·CRM·알림·Decision revision 미구현 유지
- [x] 사용자 `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- [x] 사용자 `CSight_MASTER_HANDOFF_2026-08-27.md` 미수정·미삭제·미Stage

## 5.9. Sprint 5C 완료 체크리스트

- [x] `4aefae6`에서 `feature/sprint-5c-case-resolution-external-action` 생성
- [x] ADR-0089~0095와 Resolution architecture/state/input/demo boundary 계약 고정
- [x] Case 상태와 분리된 CAS Resolution Projection과 append-only Resolution Event 구현
- [x] `human_decision_to_external_action/1.0.0`의 네 승인 Action과 두 terminal mapping 구현
- [x] Case reference와 명시적 flat `external_action_input`만 허용하고 추론·기본값·coercion 차단
- [x] 누락·잘못된 입력을 `ACTION_NEEDS_INPUT`으로 종결하고 Intent/Attempt/Result 0 보장
- [x] 서로 다른 두 번째 Decision을 자동 대체하지 않고 `MANUAL_FOLLOW_UP_REQUIRED`로 종결
- [x] Decision·Resolution request 원자 저장, immutable typed Action Intent와 두 durable outbox 구현
- [x] Resolution/Simulation exact-event 검증, claim/lease/backoff/fencing, duplicate `NOOP` 구현
- [x] network-free deterministic `DRY_RUN`, `side_effects_performed=false`, `LIVE` fail-closed 구현
- [x] Resolution/Event/Intent read-only API와 tenant scope, cross-tenant `404`, `no-store` 구현
- [x] terminal Resolution별 immutable `review_report/1.0.0`과 printable 화면 구현
- [x] numerator/denominator/sample count와 zero-denominator null을 제공하는 PoC KPI API·화면 구현
- [x] React·TypeScript·Vite console, memory-only JWT, opaque checkpoint, `/api` proxy 구현
- [x] Backend default 554, Integration 51/5 skipped, DB head `0014` drift 0 검증
- [x] Frontend lint/type/OpenAPI/build, Vitest 6, Playwright 5 검증
- [x] 7 services healthy, 8 queues consumer 1/depth 0, live Decision→validated `DRY_RUN` 검증
- [x] 실제 RabbitMQ outage의 PENDING attempt 3→CONSUMED attempt 5와 final validated 검증
- [x] 5개 demo의 증거 수준을 구분하고 Scenario 3–5를 fixture-driven UI/component-backed로 기록
- [x] Sprint 5C 완료 당시 판정을 `SYNTHETIC_MOCK_SIMULATION_DEMO`로 유지하고 Limited PoC 외부 증거를 미해결로 기록
- [x] `0a5f529 feat: add case resolution and PoC console` Commit과 동일 원격 기능 브랜치 백업, PR 없음
- [x] 사용자 소유 루트 문서 두 개 미수정·미삭제·미Stage

## 5.10. HDP-100 합성 시나리오 기술 PoC 진행 체크리스트

- [x] 가상 브랜드의 fictional `HDP-100` 수동 펌프형 경질 플라스틱 상품 범위 고정
- [x] 실제 기업·고객 자료 없이 synthetic Case 36건과 1:1 Human Gold 36건 구성
- [x] version/effective date를 가진 synthetic policy 10 clause와 deterministic rule 7개 구성
- [x] DRY-RUN·입력 누락·기능 증거 요청·Safety·Vision Timeout의 demo 5개 고정
- [x] pack artifact/hash/reference/safety 경계를 acceptance runner로 offline 9/9 검증
- [x] E3를 위치·유형 없는 `BINARY_ANY_DEFECT_CLASSIFICATION` 후보로만 명세
- [x] 담당자 보고 AP 0.884863, AUROC 0.931604, threshold 0.8984375를 출처 경계와 함께 기록
- [x] 위 E3 지표를 `report_metrics_reproduced_by_csight=false`로 표시하고 CSight 성능 주장 차단
- [x] score `>= 0.8984375`는 `HIGH_CONFIDENCE_DEFECT_CANDIDATE`, 미만은 정상 판정이 아님을 고정
- [x] binary image assessment를 기존 Detection과 분리하고 Mock 회귀 계약과 실제 E3 내부 runtime을 각각 live 연결
- [x] `20260827_0015_vision_image_assessment`를 현재 DB Head로 적용
- [x] 실제 기업 Data/Policy는 오늘 시나리오 범위에서 의도적으로 제외
- [x] 실제 E3 checkpoint package와 host-private loopback serving endpoint 확보
- [x] 실제 E3 이미지 inference, immutable model identity, latency와 threshold 계약을 synthetic connectivity image로 검증
- [x] safe stop→idempotent setup→server restart 뒤 동일 synthetic score와 Docker Worker health 200 재확인
- [ ] 실제 endpoint timeout→retry recovery와 malformed-response fail-closed를 live fault injection으로 검증
- [x] parallel Text/Vision terminal join race 수정본의 live causal 재검증 완료
- [x] 현재 branch의 정확한 default/integration/static/runtime 수치를 별도 원장 행으로 추가
- [x] 사용자 소유 루트 문서 두 개 미수정·미삭제·미Stage

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
| 2026-08-26 | Sprint 4A Closeout Commit | PASS | `6f3a667 feat: add LLM contract v2 and policy reference corpus`; Push·PR 없음 |
| 2026-08-26 | Sprint 4B Static | PASS | Ruff, Format 210, Pyright 0 errors/warnings |
| 2026-08-26 | Sprint 4B Fast Regression | PASS | 376 passed, 48 deselected, 31 warnings |
| 2026-08-26 | Sprint 4B 대상별 Test | PASS | Unit 299, Architecture 6, Contract 58, E2E+Policy API 14; 중복 포함 |
| 2026-08-26 | Sprint 4B PostgreSQL Integration | PASS | 전체 41 passed, external GPU 5 skipped, 378 deselected; policy 전용 5 passed |
| 2026-08-26 | Sprint 4B Ingestion/DB | PASS | run `252afd4b-05be-41aa-a961-ac42d91388fa` reuse, 2/24/168/168, active index 2 |
| 2026-08-26 | Sprint 4B Embedding | PASS | Qwen MPS 1024-d, external 1 passed·423 deselected, truncation/NaN/Inf/dimension mismatch 0 |
| 2026-08-26 | Sprint 4B Locked Evaluation | PASS | Dev 80/Test 40, Test 재실행 0, 세 mode result/profile artifact 검증 |
| 2026-08-26 | Sprint 4B Migration | PASS | empty→0006, 0005→0006, 0006→0005→0006, 두 DB drift 0, 임시 DB 삭제 |
| 2026-08-26 | Sprint 4B API Smoke | PASS | 두 tenant×세 mode 6건 200; provider down lexical 200/dense·hybrid 503, ready 200 |
| 2026-08-26 | Sprint 4B Runtime | PASS | 최신 image Core 6/6 Healthy, live/ready 200 |
| 2026-08-26 | Embedding Make lifecycle 첫 점검 | FAIL | 도구 셸 종료가 background descendant를 정리해 다음 호출 health 연결 거부 |
| 2026-08-26 | Embedding 전용 세션 재검증 | PASS | foreground 장기 세션에서 health/model/external embedding 1건 통과 |
| 2026-08-26 | Sprint 4B Closeout Commit | PASS | `4216028 feat: add hybrid policy retrieval baseline`; Push·PR 없음 |
| 2026-08-26 | Sprint 4C-1 Candidate Upper Bound | PASS | Dev K20 recall 0.9375, oracle MRR 1.0/nDCG 0.95164; Test 진단 1회 |
| 2026-08-26 | Qwen3 Reranker Artifact | PASS | `Qwen/Qwen3-Reranker-0.6B` revision `e61197e…5473`, Transformers 5.15.1 |
| 2026-08-26 | Qwen3 Reranker MPS Qualification | PASS_WITH_LIMITS | cold load 3.60s, K20 p50/p95 2.362/2.375s, concurrency limit 1 |
| 2026-08-26 | Sprint 4C-1 Locked Evaluation | NO_MEASURABLE_GAIN | Test Recall@10 0.925→0.925, MRR 0.53833→0.51250, nDCG 0.59841→0.59802 |
| 2026-08-26 | Sprint 4C-1 Correctness | PASS | tenant/version/effective/retired/duplicate/hard-negative/mutation 위반 0, Dev determinism 100% |
| 2026-08-26 | Sprint 4C-1 Static | PASS | Ruff 0, Format 232 files, Pyright 0 errors/warnings |
| 2026-08-26 | Sprint 4C-1 Fast Regression | PASS | 402 passed, 50 deselected, 31 warnings |
| 2026-08-26 | Sprint 4C-1 대상별 Test | PASS | Unit 319, Architecture 8, Contract 69/2 deselected, E2E 6 |
| 2026-08-26 | Sprint 4C-1 Integration | PASS | 42 passed, 5 external skipped, 405 deselected |
| 2026-08-26 | Sprint 4C-1 External Models | PASS | Embedding 1/451 deselected, Reranker 1/451 deselected, 모두 MPS |
| 2026-08-26 | Sprint 4C-1 Migration | PASS | empty/previous/round-trip to `0007`, 모든 경로 drift 0, 임시 DB 정리 |
| 2026-08-26 | Sprint 4C-1 API/Runtime | PASS | 두 tenant reranked, 기존 6 mode, down 503/no fallback, Core ready 200·6 healthy |
| 2026-08-27 | Sprint 4C-1 Closeout P1 | PASS | Format target의 reranker 누락 1건 수정, 전체 infra 234 files 확인 |
| 2026-08-27 | Sprint 4C-1 Closeout Static | PASS | Ruff, Format 234, Pyright 0 |
| 2026-08-27 | Sprint 4C-1 Closeout Regression | PASS | Fast 402/50 deselected, Unit 319, Architecture 8, Contract 69/2, E2E 6 |
| 2026-08-27 | Sprint 4C-1 Closeout Integration | PASS | 42 passed, external GPU 5 skipped, 405 deselected |
| 2026-08-27 | Sprint 4C-1 Closeout External | PASS | Embedding/Reranker 각 1 passed, 451 deselected, MPS |
| 2026-08-27 | Sprint 4C-1 Closeout Evaluation | PASS | Dev 80 재계산 mismatch 0, Test 미호출, candidate mutation 0 |
| 2026-08-27 | Sprint 4C-1 Closeout Migration | PASS | empty/previous/round-trip `0007`, drift 0, 임시 DB 3개 정리 |
| 2026-08-27 | Sprint 4C-1 Closeout API | PASS | base mode 200, reranked down 503, ready 200, Core 6 healthy |
| 2026-08-27 | Sprint 4C-2 Closeout Commit | PASS | `a282817 feat: add case-based policy retrieval query planning`; Push·PR 없음 |
| 2026-08-27 | Sprint 4C-3A Static | PASS | Format 258, Ruff 0, Pyright 0 errors/warnings |
| 2026-08-27 | Sprint 4C-3A Fast Regression | PASS | 431 passed, 3 external skipped, 47 deselected, 31 warnings |
| 2026-08-27 | Sprint 4C-3A Target Tests | PASS | Grounding unit/contract/migration 12 passed |
| 2026-08-27 | Sprint 4C-3A Integration | PASS | 42 passed, 5 external GPU skipped, 434 deselected |
| 2026-08-27 | Sprint 4C-3A Structural Evaluation | PASS | Grounding 50 + Injection 30, 위반 0, replay 100% |
| 2026-08-27 | Sprint 4C-3A Semantic Evaluation | SKIPPED | `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| 2026-08-27 | Sprint 4C-3A Migration | PASS | empty/previous/round-trip `0009`, drift 0, 임시 DB 3개 정리 |
| 2026-08-27 | Sprint 4C-3A Live Async | PASS | PostgreSQL/RabbitMQ/Celery, 10 citations/statements, replay 200, tenant 404 |
| 2026-08-27 | Sprint 4C-3A Provider Down | PASS | stable unavailable error, result 0, Mock fallback 0 |
| 2026-08-27 | Sprint 4C-3A Runtime Cleanup | PASS | 대상 run 3·result 2·outbox 3·item 10·pack 1 삭제, 대상 run 0 |
| 2026-08-27 | Sprint 4C-3A Compose Contract | PASS | 기본 Worker가 `grounded-explanation` queue를 소비하도록 보완, config render 통과 |
| 2026-08-27 | Sprint 4C-3A Docker Rebuild | BLOCKED | 외부 registry metadata 응답 정지; Dockerfile diff 0, 기존 Core 6 healthy |
| 2026-08-27 | Sprint 4C-3A Docker Rebuild Retry | PASS | 최신 image build, Dockerfile diff 0, Core 6 healthy, live/ready 200 |
| 2026-08-27 | Sprint 4C-3A Docker Queue/E2E | PASS | 4 queues consumer 1·depth 0, 10 citations/statements, replay 200, tenant 404 |
| 2026-08-27 | Sprint 4C-3A Duplicate Delivery | PASS | terminal event 2회 재전달 뒤 run 1·result 1·queue depth 0 |
| 2026-08-27 | Sprint 4C-3A Independent Closeout | PASS | P0 0, P1 0; 전체 Gate 통과; semantic model quality는 SKIPPED 유지 |
| 2026-08-27 | Sprint 5A Static | PASS | Ruff 0, Format 296, Pyright 0 errors/warnings/informations |
| 2026-08-27 | Sprint 5A Default Regression | PASS | 456 passed, 55 deselected, 31 warnings |
| 2026-08-27 | Sprint 5A Target Suites | PASS | Architecture 9, Unit 356, Contract 85/2 skipped, E2E 6, Policy API/core 19 |
| 2026-08-27 | Sprint 5A Integration first run | ENV_CONTENTION | 장기 Dispatcher가 test outbox를 선점해 1 failed, 43 passed, 5 skipped |
| 2026-08-27 | Sprint 5A Integration isolated | PASS | Worker/Dispatcher 일시 정지 후 44 passed, 5 external-GPU skipped, 462 deselected |
| 2026-08-27 | Sprint 5A Migration | PASS | empty/previous/round-trip `0010`, drift 0, 임시 DB 0; live DB head/drift 0 |
| 2026-08-27 | Sprint 5A Rule DB Audit | PASS | active 2, set 2, rule 24, source 24; orphan/mismatch/missing source/final effect 0 |
| 2026-08-27 | Sprint 5A Frozen Evaluation | PASS | Dev80/Test40 모든 metric 1.0; tenant/future/final-decision 위반 0 |
| 2026-08-27 | Sprint 5A Docker Runtime | PASS | 최종 image, Core 6 healthy, live/ready 정상, application queue 5개 consumer 1 |
| 2026-08-27 | Sprint 5A Live Async | PASS | rules 12, replay 200, duplicate NOOP, tenant 404, Mock Vision NOT_EVALUATED |
| 2026-08-27 | Sprint 5A Git Handoff | PASS | Branch 정확, Sprint 5A Commit·Push·PR 없음, Kaputt 미Stage 보존 |
| 2026-08-27 | Sprint 5B Static | PASS | Ruff 0, Format 315, Pyright 0 errors/warnings/informations |
| 2026-08-27 | Sprint 5B Default Regression | PASS | 484 passed, 57 deselected, 31 warnings |
| 2026-08-27 | Sprint 5B Integration | PASS | 46 passed, 5 external-GPU skipped, 490 deselected, 3 warnings |
| 2026-08-27 | Sprint 5B Focus | PASS | Human Review unit/HTTP/runtime 28, architecture 포함 focus 37, repository 2 |
| 2026-08-27 | Sprint 5B Evaluation | PASS | Dev60/Test30 sealed, 9 workflow metrics 1.0, 9 violation counts 0 |
| 2026-08-27 | Sprint 5B Migration | PASS | Empty→0011, 0010→0011, 0011→0010→0011, drift 0, 임시 DB 0 |
| 2026-08-27 | Sprint 5B Docker Runtime | PASS | 최신 image, Core 6 healthy, application queue 6개 consumer 1/depth 0 |
| 2026-08-27 | Sprint 5B Live Async/API | PASS | task/packet/created/claim/resolve/decision/basis 각 1, duplicate 409/NOOP, tenant 404 |
| 2026-08-27 | Sprint 5B Git Handoff | PASS | Branch `feature/sprint-5b-human-review-workflow`, Commit·Push·PR 없음, Kaputt 제외 |
| 2026-08-27 | Sprint 5B Reliability Static | PASS | Ruff 0, Format 324, Pyright 0 |
| 2026-08-27 | Sprint 5B Reliability Regression | PASS | Default 516 passed/59 deselected; Integration 48 passed/5 external-GPU skipped/522 deselected |
| 2026-08-27 | Sprint 5B Reliability Migration | PASS | Empty→0012, 0011→0012, 0012→0011→0012, drift 0, 임시 DB 잔존 0 |
| 2026-08-27 | Sprint 5B Broker Recovery | PASS | RabbitMQ 중단 시 pending/backoff, 재기동 후 CONSUMED; duplicate 두 번 `NOOP`, Result 불변 |
| 2026-08-27 | Sprint 5B Reliability Runtime | PASS | DB head 0012, Core 6 healthy, application queue 6개 consumer 1/depth 0, live smoke PASS |
| 2026-08-27 | Sprint 5B Commit·Remote Backup | PASS | `4aefae6 feat: add human review workflow`; `origin/feature/sprint-5b-human-review-workflow` Push, PR 없음 |
| 2026-08-27 | Sprint 5C Backend Static | PASS | Ruff, Format, Pyright 최종 통과 |
| 2026-08-27 | Sprint 5C Default Regression | PASS | 554 passed, 62 deselected |
| 2026-08-27 | Sprint 5C Integration | PASS | 51 passed, 5 external-GPU skipped, 560 deselected |
| 2026-08-27 | Sprint 5C Frontend Static·Contract | PASS | ESLint, TypeScript, generated OpenAPI check, production build 통과 |
| 2026-08-27 | Sprint 5C Frontend Tests | PASS | Vitest 6, Playwright 5; Playwright는 intercepted API fixture, Scenario 3–5 live causal E2E 아님 |
| 2026-08-27 | Sprint 5C Migration | PASS | PostgreSQL head `0014`, schema drift 0 |
| 2026-08-27 | Sprint 5C Docker Runtime | PASS | 7 services healthy, 8 application queues 각각 consumer 1/depth 0 |
| 2026-08-27 | Sprint 5C Live Resolution | PASS | Decision→Resolution→`DRY_RUN` validated, duplicate `NOOP`, `cases.status` 불변, cross-tenant `404` |
| 2026-08-27 | Sprint 5C Broker Recovery | PASS | 실제 Rabbit outage에서 request `PENDING` attempts 3→복구 뒤 `CONSUMED` attempts 5, final validated |
| 2026-08-27 | Sprint 5C Commit·Remote Backup | PASS | `0a5f529 feat: add case resolution and PoC console`; `origin/feature/sprint-5c-case-resolution-external-action` Push, PR 없음 |
| 2026-08-27 | Sprint 5C Limited PoC Gate | BLOCKED | 구현 Gate는 통과했으나 실제 Data/Policy/Vision·Privacy·Shadow·Qwen 외부 증거 미확보 |
| 2026-08-27 | Current Status HTML | PASS | 단일 HTML 200 응답, 외부 asset 0, 반응형·인쇄/PDF 레이아웃과 내부 데모/PoC Gate 구분 |
| 2026-08-27 | HDP-100 Scenario Dataset | PASS_WITH_SCOPE | fictional product, synthetic Case/Gold 36/36, demo/dev/test 5/21/10; 실제 기업·고객 Data 0 |
| 2026-08-27 | HDP-100 Synthetic Policy | PASS_WITH_SCOPE | version 1.0.0, effective 2026-08-27, 10 clauses, 7 rules; 법률·상업 효력 없음 |
| 2026-08-27 | HDP-100 Offline Acceptance | PASS | 필수 artifact/hash, 36 unique Case/Gold, policy, 5 safety demo, binary model boundary 9/9 |
| 2026-08-27 | E3 Offline Report Metrics | REPORTED_NOT_REPRODUCED | AP 0.884863, AUROC 0.931604, threshold 0.8984375; 담당자 보고 수치이며 CSight 미재현 |
| 2026-08-27 | Binary Vision Contract Live | PASS_WITH_SCOPE | 실제 E3가 아닌 deterministic Mock any-defect score/threshold 계약만 live 연결 |
| 2026-08-27 | Actual E3 Runtime | BLOCKED | `best.pt` checkpoint package, serving endpoint와 endpoint reference 모두 NOT_AVAILABLE |
| 2026-08-27 | Vision Assessment DB | HEAD_APPLIED | 현재 PostgreSQL Head `0015`; `vision_image_assessments` additive schema |
| 2026-08-27 | Parallel Join Focused Regression | PASS_WITH_SCOPE | 실제 PostgreSQL barrier 회귀 1 passed/14 deselected; live causal 재검증 완료를 뜻하지 않음 |
| 2026-08-27 | Parallel Text/Vision Join | PENDING_REVERIFICATION | live race 수정 후 재검증 중; 현재 branch 최종 causal 결과와 수치 미확정 |
| 2026-08-27 | Current Branch Full Regression | PENDING_REVERIFICATION | 기존 Sprint 5C의 554 default/51 integration 수치는 보존; HDP-100 branch 새 수치로 대체하지 않음 |
| 2026-08-27 | HDP-100 Backend Static | PASS | Ruff, Format 365, Pyright 0 errors·0 warnings·0 informations |
| 2026-08-27 | HDP-100 Default Regression | PASS | 585 passed, 65 deselected, 36 non-blocking deprecation warnings |
| 2026-08-27 | HDP-100 Integration | PASS | 54 passed, 5 external-vLLM GPU skipped, 591 deselected; disposable DB 잔존 0 |
| 2026-08-27 | HDP-100 Frontend | PASS | lint·TypeScript·OpenAPI sync·production build, Vitest 9, Playwright fixture scenario 5 |
| 2026-08-27 | HDP-100 Live Binary Vision | PASS_WITH_SCOPE | 새 parallel Run `18451c65-ec11-4beb-a814-a52f695f8505` SUCCEEDED; Result/Assessment/Detection 1/1/0, threshold 0.8984375, Mock score 0.965449 |
| 2026-08-27 | Parallel Join Orphan Recovery | PASS | 기존 orphan Run `e5d01e06-5f93-44b5-959e-1c18da81eb71`의 terminal event redelivery가 NOOP으로 parent를 SUCCEEDED 복구; Result/Assessment/Detection 1/1/0 |
| 2026-08-27 | HDP-100 Runtime Health | PASS | DB Head `0015`, 7 services healthy, 8 application queues consumer 1/depth 0, API·Web HTTP 200 |
| 2026-08-28 | HDP-100 Backend Static Reverification | PASS | Ruff PASS, Format 365 files, Pyright 0 |
| 2026-08-28 | HDP-100 Default Regression Reverification | PASS | 603 passed, 65 deselected |
| 2026-08-28 | HDP-100 Integration Reverification | PASS | 54 passed, 5 external-GPU skipped, 609 deselected; disposable DB 잔존 0 |
| 2026-08-28 | HDP-100 Frontend Reverification | PASS | lint·typecheck·generated OpenAPI sync·production build, Vitest 10, Playwright fixture scenario 5 |
| 2026-08-28 | HDP-100 Scenario Offline Reverification | PASS | acceptance 9/9; pack hash `6be7ad00ba4b92bd99fbcb0ab6c7b9163e387aa8ccd734751c479a2352c24ef1` |
| 2026-08-28 | Actual E3 Runtime Reverification | BLOCKED | endpoint, checkpoint package, endpoint reference 부재; runtime probe 미실행 |
| 2026-08-28 | HDP-100 Live Binary Vision Reverification | PASS | Run `fc249b72-92b4-4160-adee-2c9b0b66b092` SUCCEEDED; Mock score 0.961864, threshold 0.8984375, Detection 0, automatic Decision false |
| 2026-08-28 | HDP-100 Runtime Health Reverification | PASS | DB Head `0015`, 7 services healthy, 8 application queues consumer 1/depth 0 |
| 2026-08-28 | HDP-100 HTTP Surfaces | PASS | API·Web·상태 HTML 각각 HTTP 200 |
| 2026-08-28 | HDP-100 Git Commit·Remote Backup | NOT_RUN | 로컬 변경은 최종 검증됐으나 기능 Commit과 원격 기능 브랜치 Push는 아직 pending |
| 2026-08-28 | HDP-100 Git Commit·Remote Backup | PASS | `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d feat: add hard-plastic scenario PoC`; local·`origin/feature/scenario-poc-hard-plastic` 동일 SHA, PR·`develop` 병합 미실행 |
| 2026-08-28 | HDP-100 Status Closeout·Remote Backup | PASS | `5c152fd0d1e97eba3b41b2ecea1cff7811814d90 docs: close out hard-plastic scenario PoC`; local HEAD·원격 기능 브랜치 일치, PR 없음 |
| 2026-08-28 | E1–E3 Weight Transfer Integrity | PASS | 전달 3개 checkpoint의 SHA256SUMS 재계산 일치; E3 size 264,918,248와 SHA `49e8a64c…1037e`가 canonical manifest와 일치 |
| 2026-08-28 | E3 Safe Offline Load | PASS | unsafe globals 0, `weights_only=True`·CPU mmap, exact root/config/225 float32 tensor/22,056,961 parameter/finite/strict key 검증; runtime model fetch 0 |
| 2026-08-28 | E3 Host Runtime | PASS_WITH_SCOPE | loopback `127.0.0.1:8093`, MPS float32, direct HTTP synthetic score 0.5347466/threshold 0.8984375, Detection 0; 제품 qualification 아님 |
| 2026-08-28 | E3 Core Causal Integration | PASS_WITH_SCOPE | Run `893f8927-7c71-4246-936b-5c752493ffc4` SUCCEEDED; exact model/version/SHA, BELOW_HIGH_CONFIDENCE_THRESHOLD, automatic Decision 0 |
| 2026-08-28 | E3 Failure Boundaries | PASS_WITH_SCOPE | wrong task와 MIME/content mismatch HTTP 422, sparse hash-drift가 `torch.load` 전 차단, symlink 거부, safe stop/setup/restart와 score 재현 통과; 실제 timeout recovery는 미실행 |
| 2026-08-28 | E3 Runtime Backend Regression | PASS | Ruff 0, Format 374, Pyright 0, Default 605 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/611 deselected, disposable DB 0 |
| 2026-08-28 | E3 Runtime Frontend Regression | PASS | lint·typecheck·OpenAPI·build, Vitest 10, Playwright fixture E2E 5 통과 |
| 2026-08-28 | E3 Runtime Live Health | PASS | DB Head `0015`, E3 health 200, Core 7 services healthy, 8 queues consumer 1/depth 0, API·Web·상태 HTML HTTP 200 |
| 2026-08-28 | E3 Status Dashboard Browser QA | PASS | 실제 E3 연결/제품 qualification 차단 문구를 브라우저 DOM에서 확인하고 기존 상태 탭을 갱신 |
| 2026-08-28 | E3 Runtime Git Handoff | NOT_RUN | 현재 변경은 로컬 미Commit·미Push; checkpoint와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | Local Demo Admin Identity | PASS | tenant `csight`, user `csight@csight.demo`, active `ADMIN` 1계정/1역할; token·me HTTP 200, Argon2 hash 저장 확인 |
| 2026-08-28 | Cloudflare Public Demo Route | PASS_WITH_SCOPE | `doongdoong.org`·`www`의 game 3000/WS 3001 ingress를 CSight Web 8080으로 전환; 외부 system-info·token·me 200와 브라우저 Login DOM 확인, Access 미적용 |
| 2026-08-28 | E3 Top-100 Package Integrity | PASS_WITH_SCOPE | JPEG 100장 SHA/decode/2048²/RGB/EXIF·ICC 0, exact duplicate 0; package tree `4543f49f…cb132`, license·annotation provenance는 미제공 |
| 2026-08-28 | E3 Top-100 Direct Replay | PASS_WITH_SCOPE | 실제 E3 100/100 완료, source 0.5와 frozen 0.8984375 모두 100/100; score 0.9980715~0.9999757, selected-positive라 일반 metric 아님 |
| 2026-08-28 | E3 Top-100 Core Sample | PASS_WITH_SCOPE | 비식별 hard-plastic rank 003/032/054/058/078/080 6건 모두 SUCCEEDED; Evidence SHA·direct/Core score delta 0·Detection 0 |
| 2026-08-28 | E3 Top-100 Post-run Safety Audit | PASS | 6 Case 모두 Human Review Task/Resolution Event/Action Intent 0, Resolution GET 404; raw image Git·public Web 복사 0 |
| 2026-08-28 | E3 Top-100 Replay Report | PASS | local-only report hash `9400509e18689d6696e303a7f30a803cd1252872d21ff123c28b0b50e1d9d2bf` 재계산 일치; 원본·report는 Git 제외 |
| 2026-08-28 | E3 Top-100 Tool Static·Focused | PASS | Ruff 0, Format 376 files, Pyright 0; 새 unit/architecture focus 9 passed, E3 runtime 5 passed |
| 2026-08-28 | E3 Top-100 Default Regression | PASS | 612 passed, 65 deselected, 기존 deprecation warning 36 |
| 2026-08-28 | E3 Top-100 Status HTML | PASS | parse error·duplicate ID·missing anchor·external asset 0, local status·external login HTTP 200; Browser 1324px에서 카드 4·가로 overflow·console warning/error 0, 기존 console-link 세로 배치 수정 |
| 2026-08-28 | E3 Top-100 Integration Suite | NOT_RUN | App/API/Migration 계약 변경 없음; 실제 E3 100건과 Core 6건 causal run으로 이번 변경을 검증, 기존 54 integration 수치는 재사용하지 않음 |
| 2026-08-28 | E3 Normal Reference Audit·Replay | PASS_WITH_SCOPE | 사용자 제공 JPEG 77/77 SHA/decode/2048² RGB·EXIF/ICC 0·Top-100 overlap 0; 실제 E3 77/77이 0.8984375 미만. 사용자 진술 외 Gold·license·provenance는 없음 |
| 2026-08-28 | Realistic Internal Demo 6:4 | PASS_WITH_SCOPE | 결함 selected-correct 6 + 정상 참고 4를 10개 자연어 Case와 private Evidence로 고정; 실제 E3 10/10, 후보 6·기준 미만 4, 정상 성능·실제 분포 평가 아님 |
| 2026-08-28 | Private Evidence Content | PASS | 인증·tenant/Case scope·AVAILABLE·bounded read·size/SHA fail-closed endpoint와 Web Blob preview 구현; 10/10 저장 Object를 frozen source SHA로 재검증 |
| 2026-08-28 | `csight` Synthetic Policy Runtime | PASS | fictional corpus 12 Document/84 Clause/84 Qwen embedding/ACTIVE index 1, Rule/Source 12/12; local-only fail-closed prepare 2회 모두 신규 0·exact reuse |
| 2026-08-28 | Representative Policy→Review Flow | PASS_WITH_SCOPE | 결함 1·기준 미만 1이 Text v2→RAW Top-3→Grounding→Policy `SUCCEEDED`, matching Review 2 `PENDING`; E3는 policy input과 연결하지 않았고 Decision·Resolution·Action 0 |
| 2026-08-28 | Realistic Demo Backend Regression | PASS | Ruff PASS, Format 382, Pyright 0; default 648 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/654 deselected, disposable DB 제거 |
| 2026-08-28 | Realistic Demo Frontend Regression | PASS | lint·typecheck·OpenAPI sync·build, Vitest 32, Playwright fixture scenario 5; 공개 Login DOM·console error 0 |
| 2026-08-28 | Realistic Demo Git Handoff | NOT_RUN | 이번 변경은 로컬 미Commit·미Push·PR 없음; raw image·checkpoint·local reports와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | R1 Visual-Aligned Seed Replay | PASS | R1 10건 seed/replay, Evidence integrity 10/10, 신규 workflow row 0; report hash `6a7b9af27016ea9a88141878cdbadaca71b2e3ea660f9b47c9d944c4f7002dba` |
| 2026-08-28 | CSight Commerce Policy `2.0.1` | PASS | 신규 8 Document·52 Clause·25 Rule/35 Source; 전체 20/136. prepare 1회 insert 25, 2회째 insert 0·exact reuse, `2.0.1` sole active |
| 2026-08-28 | Faulty Policy `2.0.0` Recovery | PASS | immutable hash 불일치 원인을 source 정렬로 확정; faulty `2.0.0`·failed Run은 삭제 없이 RETIRED 감사 이력, clean ingest는 v1+2.0.1만 생성 |
| 2026-08-28 | R1 Representative Policy→Review | PASS | 수리·Safety·단순변심 3건이 Text v2→RAW Top-3→Grounding→Policy `2.0.1` SUCCEEDED, Review 3 PENDING; Decision·Resolution·Intent·Attempt·Result 0 |
| 2026-08-28 | R1 Backend Final Regression | PASS | Ruff PASS, Format 384, Pyright 0; default 658 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/664 deselected, disposable DB 제거 |
| 2026-08-28 | R1 Frontend Final Regression | PASS | lint·typecheck·OpenAPI sync·build PASS, Vitest 39, Playwright fixture 5; 공개 Login DOM·가로 overflow·console warning/error 0 |
| 2026-08-28 | R1 Runtime Reverification | PASS | 12:48 KST DB Head 0015, E3·Embedding MPS와 Core 7 services healthy, API live/ready·Web health PASS, Core `VISION_PROVIDER=remote` identity 일치 |
| 2026-08-28 | R1 Git Handoff | NOT_RUN | 사용자 지시 없음; 로컬 미Commit·미Push·PR. raw image·checkpoint·local report와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | Consultant UX·Continue 422 Regression | PASS_WITH_SCOPE | UTC/KST policy-date 원인을 API log·DB rule 효력일로 확정; OpenAPI sync·lint·typecheck·build, Vitest 42, Playwright fixture 5 PASS; 13:22 KST Core 7 healthy·API/Web/외부 tunnel health PASS. rebuild로 memory token이 초기화되어 인증 Case 수동 클릭은 미실행 |
| 2026-08-28 | Human-confirmed Quick Review Regression | PASS | OpenAPI sync·lint·typecheck·build, Vitest 15 files/45 tests, Playwright 5 PASS. Scenario 1이 정확한 CAS Claim v1→Resolve v2, `APPROVE_REPAIR`, rule+citation basis, Report 자동 navigation을 검증; Safety Reviewer 차단/Admin quick review 유지 |
| 2026-08-28 | Quick Review Runtime Surface | PASS | 13:50 KST 재빌드 후 Core 7 services healthy, API ready·Web health·외부 tunnel health PASS; 공개 Login title/DOM, browser console warning/error 0. 실제 인증 Decision 클릭은 데이터 변경 방지를 위해 NOT_RUN |
| 2026-08-28 | Refund Processing Confirmation UI | PASS | Shopify·Stripe·국내 전자상거래법 공식 자료의 공통 운영 필드를 참고해 특정 기업 복제 없이 구현. typecheck·lint·build PASS, Vitest 17 files/49 tests, Playwright fixture 5 PASS, 1440px full-page visual QA PASS |
| 2026-08-28 | Refund Confirmation Runtime Surface | PASS | 14:04 KST Web/API rebuild 후 DB Head `0015`, Core 7 services healthy, API readiness OK, local/public Login HTTP 200; 실제 Human Decision·환불 실행은 NOT_RUN |
| 2026-08-28 | GitHub Branch Stage Audit | PASS | 원격 7 branches. PoC `5c152fd`는 main/develop보다 21 commits, Sprint 5C보다 2 commits ahead이고 latest CI success. Vision `3e2d596`은 PoC와 55/21 diverged, latest CI success·Draft PR #4. PR #2 open, PoC PR·release tag 없음 |
| 2026-08-28 | Natural UI·Communication·Data Assets | PASS_WITH_SCOPE | 자연어 decision/status UI, terminal Report 기반 EMAIL simulation v1.1, tenant append-only allowlist asset. 기본 672 PASS, 격리 Migration 2 PASS, Web 57 PASS, Head 0016, live side effects 0 |
| 2026-08-28 | Runtime Memory Ready Baseline | PASS | 16:28 KST 단일 시점: CSight 귀속 약 4.21 GiB/32 GiB(13.16%), Vision 1,570 MiB, Embedding 1,732.5 MiB, Docker Core 961.95 MiB, tunnel 48.42 MiB. memory-pressure 여유 80%, swap-in/out 0; Case batch/동시 부하는 미실행 |
| 2026-08-28 | Kaputt Local Source Audit | PASS | 4090 Node `/home/data/datasets/kaputt` 406 GiB, extracted 101 GiB. Query image train 85,326·validation 4,874·test 10,067로 Parquet 행과 일치; `plastic_hard` 10,095, defect 1,323·negative 8,772 |
| 2026-08-28 | Qwen3.8 VLM Offline Sample | PASS | 별도 native VLM endpoint가 RTX 4090에서 healthy, prompt 1.2.0 균형 표본 4/4 schema success·요청 9.3–10.8초·민감 패턴 0. 사람 점검 상품 유형 유용성 1/4, defect positive 두 건 모두 `UNCERTAIN`; 전체 Batch 미실행 |
| 2026-08-28 | Qwen3.8 VLM Resource Recovery | PASS | 결과 SHA-256 `390f7d32a1b9a689d4071c59d2e8c0493851c7ea5ea3659f9af7ab58913b0d57`; append-only sample을 private derived 경로에 보존하고 전용 Container exit 0, GPU 22,365→95 MiB |
| 2026-08-28 | Qwen Query+Reference+Prompt Contract | PASS | 동일 `item_identifier`의 Query/Reference Crop 4쌍 선택 추출, vLLM image 2개 제한과 schema 2.0.0 적용. prompt 2.0.1 4/4 구조 성공·민감 패턴 0·결과 SHA `159f5ded7eb9559d5b322ca9d24d48cfc117ed4c94a922f89c7145cb8bac3811` |
| 2026-08-28 | Qwen Paired Label Quality Gate | FAIL | 사람 점검 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2. 10,095건 전체 Batch를 중단하고 Qwen을 결함 Label/E3 대체 경로에서 제외 |
| 2026-08-28 | Qwen3.8 VLM Runtime Restart | PASS | 18:42 KST 전용 Container healthy, 인증 model API 200·exact served identity 확인. RTX 4090 21,511/24,564 MiB, utilization 0%, 39°C; Tailscale private `:18001` |
| 2026-08-28 | Kaputt Paired 30 Crop Preparation | PASS | deterministic defect 15/negative 15; Query Crop 30·same-item Reference Crop unique 28 준비. 31.6/41.6 GiB archive에서 missing 26/24만 선택 추출 |
| 2026-08-28 | Qwen Paired Defect 30 | FAIL | 30/30 schema success지만 UNCERTAIN 26, TP/FP/TN/FN 0/2/0/2, coverage 13.3%. 공식 Label/E3 대체 불가, 결과 SHA `e53a516b8ffb5400def2f490f3376716e18d89e2029670e6782a14f408deb2a6` |
| 2026-08-28 | Qwen Product Metadata 30 | PASS | 결함 필드 없는 별도 schema 30/30 success, specific name 25·uncertain 5, 금지 필드·민감 패턴 0, p50 8.5초·p95 10.0초, SHA `7ddc9197c957f9e81b5560476a789f06d555e346ff8dc0df734c076abfef846a` |
| 2026-08-28 | Qwen Product Taxonomy Gate | FAIL | Contact Sheet에서 supplement/cleaning-chemical/pet category 공백과 mismatch 확인. Human Gold 없이 25/30 specificity를 accuracy로 해석하거나 Catalog에 자동 반영하지 않음 |
| 2026-08-28 | PoC Closed-set Registry v1 | PASS_WITH_SCOPE | 상품군 4·결함군 3, 사람 승인 SHA Allowlist 10건. 실제 source identity/label 10/10 PASS, E3 채택 margin defect>=0.95/reference<=0.10. 현재 상품군 2/4·결함군 3/3 표현, 성능평가 아님 |
| 2026-08-28 | PoC Closed-set Registry v2 Expansion | PASS_WITH_SCOPE | 새 SHA Allowlist 10건을 실제 source와 대조하고 E3 채택 10/10. v1+v2 최신 팩은 20건(12:8), 상품군 4/4·결함군 3/3 표현. v3 seed/replay와 workflow boundary 0 통과, 클래스별 정확도 평가는 아님 |

## 8. 미해결 사항과 사용자 결정

- HDP-100은 가상 브랜드의 fictional product이고 36 Case/Gold, 10 clause/7 rule, 5 demo가 모두
  합성이다. Offline acceptance 9/9는 artifact와 안전 계약의 완전성을 뜻하며 실제 고객/상품
  성능이나 실제 기업 정책 타당성을 뜻하지 않는다.
- E3 AP 0.884863, AUROC 0.931604, threshold 0.8984375는 담당자가 제공한 offline 보고서 수치다.
  CSight가 전달 checkpoint로 개별 forward와 threshold 적용은 실행했지만 held-out dataset metric을
  재계산하지 않았으므로 `SUPPLIED_OFFLINE_REPORT_WITH_LIMITATIONS`는 유지한다.
- E3 score가 0.8984375 이상이면 고신뢰 `defect candidate`일 뿐 결함 유형·위치·최종 결정을
  뜻하지 않는다. 미만은 `정상`이나 결함 없음이 아니라 고신뢰 후보 기준 미만이다.
- 현재 live 연결은 exact SHA가 고정된 E3 checkpoint를 host-native loopback endpoint로 띄우고
  Docker Worker가 호출하는 경로까지 통과했다. 합성 이미지 score 0.5347466은 threshold 미만이라
  정상 판정 없이 사람 검토로 수렴했다. 이는 제품별 정확도나 domain-shift qualification이 아니다.
- 전달 Top-100은 무결성 검사와 실제 E3 100/100 재실행, hard-plastic Core 6/6을 통과했다. 그러나
  E3가 이미 맞힌 defect 100/normal 0만 역선택한 자료라 accuracy·recall·specificity·FPR·calibration을
  산출하지 않는다. hard-plastic 14장도 모두 major defect이고 HDP-100 다섯 Human Gold를 대체하지 않는다.
- 사용자 제공 정상 참고 폴더 77장은 실제 E3에서 모두 frozen threshold 미만이었고 그중 4장을
  현실형 내부 데모에 섞었다. 그러나 정상 label의 근거는 사용자 진술뿐이고 무작위 표본·독립 Gold·
  license·원소유자·dataset revision이 없으므로 specificity/FPR 또는 `정상 확인` 근거가 아니다.
- 현실형 최신 20건의 12:8은 화면 시연을 위해 의도적으로 고른 비율이다. 결함 12장은 selected-correct
  positive, 저점수 참고 8장은 낮은 score의 pixel-reviewed allowlist이므로 실제 발생률·정확도·비교
  성능으로 해석하지 않는다. raw image는 private Evidence에만 저장하고 Git·공개 Web static에 복사하지 않는다.
- `poc_closed_set/2.0.0` 확장으로 네 상품군을 모두 화면에 표현하지만 표본 수가 작고 선별 편향이
  있으므로 상품군별 정확도·대표성 검증이 아니다. 세 결함군은 원천 multi-label로 나타나며 E3 결함 유형 예측 증거가 아니다.
  E3 `0.95/0.10`은 선별 여유폭이고 운영 threshold `0.8984375`를 변경하지 않는다.
- 가상 상품명·SKU·가격대 20건은 사진의 일반 외관과 기존 문의를 연결한 표시 전용 합성 카탈로그다.
  실제 상품 식별·시장조사·판매가·환불 금액이 아니며 LLM·Policy·Resolution·External Action 입력으로
  사용하지 않는다. 카탈로그에 없는 Case는 상품을 추정하지 않고 기존 `product_ref`만 표시한다.
- 새 10장은 사진별 제품군 육안 매칭, 개인 이름이 보이는 rank 61과 모호한 rank 56 제외,
  SHA/권리 경계와 E3 결과 고정을 거쳐 active catalog에 추가했다. 추가 확장은 같은 승인 절차를 반복한다.
- 실제 E3 결과는 `attributes.realistic_demo.policy_input_linkage=NOT_LINKED_TO_POLICY_INPUT`으로
  고정했다. 대표 3건의 Text/검색/Grounding/Policy/Human Review는 실제 비동기 경로를 통과했지만
  정책 판단이 Vision score를 사용했다는 뜻이 아니며, Review Packet이 최종 근거 snapshot이다.
- UI는 Retrieval↔Grounding의 직접 연결만 표시하고 Policy는 Text analysis 연결만 확정한다.
  다중 실행이 있을 때 Grounding↔Policy exact chain을 추정하지 않으며, 최신 실패 실행이 이전 성공
  결과를 가리지 않도록 실패 단계만 새 idempotency key로 재시도한다.
- Top-100 package에는 license, 원소유자, dataset revision, annotation provenance와 공개 재배포
  권리가 없다. 상품 label·barcode가 보이고 rank 061에는 개인 이름이 있어 Core 표본에서 제외했다.
  원본은 Git·Docker context·공개 Web에 복사하지 않고 내부 비상업 연결 재현에만 사용한다.
- parallel Text/Vision terminal join race는 parent Run row lock과 terminal redelivery
  reconciliation으로 수정했다. PostgreSQL 동시성 회귀와 새 live Run이 통과했고, 실제로
  고립됐던 기존 Run도 동일 event 재전달의 `NOOP` 경로에서 `SUCCEEDED`로 복구됐다.
- 실제 기업 Data와 실제 기업 Policy 반입은 오늘 HDP-100 합성 시나리오 범위에서 의도적으로
  제외했다. 따라서 실제 고객·정책·Privacy·Shadow 근거를 확보했다는 주장으로 승격하지 않는다.
- Sprint 5C 구현과 내부 데모 Gate는 통과했고 현재 판정은
  `SYNTHETIC_REAL_E3_TECH_DEMO`다. 실제 기업 정책·Case·사용자 Query 분포와 ROI를 검증하지
  않았으며 Local LLM은 `LOCAL_POC`, Vision은 `E3_RUNTIME_CONNECTED_NOT_PRODUCT_QUALIFIED`다.
- Kaputt 기반 E3는 교육·과학적 CV 연구 범위의 비상업 합성 기술 데모로만 사용한다. 사용자
  지시에 따라 Web 콘솔은 현재 `doongdoong.org` 공개 터널에 연결됐지만 E3 endpoint 자체는
  loopback에 남아 있다. 실제 데이터 업로드, 고객·상업 파일럿과 성능 홍보는 권리·법률 승인 전 차단한다.
- 공식 Kaputt Query 이미지는 이미 전량 추출돼 있고 Reference image/crop/mask는 압축 archive에
  있다. 동일 `item_identifier`의 Query/Reference Crop 4쌍을 선택 추출해 사진 2장+비교 Prompt로
  재검증했지만 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2였다. 공식 defect label/E3를
  대체하거나 10,095건 전체를 자동 라벨링하지 않으며, Qwen derived label은 선택적 후보 데이터로만
  취급한다.
- 후속 paired 30건에서도 generic VLM 결함 task는 coverage 13.3%, TP 0이어서 품질 실패가
  확정됐다. 분리한 상품 메타데이터 task는 특정 generic name을 25/30 제안했지만 이는 specificity이지
  정확도가 아니다. 현재 category enum에 supplement, cleaning/chemical, pet-care가 없어 이름과
  category가 어긋나는 사례가 있으며, Human Gold 검수 전 자동 catalog/시나리오 반영을 금지한다.
- Limited PoC 승격에는 고객/상품/결함 범위, 비식별 실제 Case 30건 이상과 Human Gold,
  버전·효력일이 있는 실제 정책, 개인정보 Retention·삭제·EXIF·접근 승인, 실제 Vision qualification
  또는 명시적 제외, 실제 Qwen Extraction·Grounding 재평가와 Shadow 비교가 모두 필요하다.
- 실제 `LIVE` 외부 실행, 환불·교환·재배송·수리·결제·CRM·고객 알림, Case Closure, Decision
  amendment, Review 단계 입력 보완, 자동 assignment/SLA, OIDC/RLS는 구현하지 않았다.
- 고객 안내 메일은 발송 결과가 아니라 `SIMULATED_NOT_SENT` 상태의 화면·감사 기록이다. 실제 SMTP,
  수신자 전송, 배송 성공률은 구현·검증하지 않았고 UI도 `실제 미발송`으로 고정한다.
- 데이터 자산은 고객 문의 원문·이름·전화·주소·담당자 rationale을 제외한 allowlist다. 현재 `csight`
  표본은 6건으로 기준선 최소 30건보다 적어 드리프트 수치를 표시하지 않는다. 30건은 기준선 준비,
  60건은 비교 구간 준비 Gate일 뿐 실제 성능 보장을 뜻하지 않는다.
- `csight` Admin은 사용자가 지정한 짧은 데모 Credential을 사용하며 Cloudflare Access는 없다.
  Web이 공개 터널에 연결된 현재 상태는 임시 합성 시연에만 사용하고, 외부 공유 전에는 Access를
  적용하거나 Credential을 강화해야 한다. 원장과 Git에는 비밀번호를 기록하지 않는다.
- 5개 Playwright demo는 intercepted API fixture를 사용한다. Scenario 1은 별도 live backend causal
  경로가 있고 Scenario 2는 PostgreSQL integration 경로가 있지만, Scenario 3–5는
  fixture-driven UI/component-backed이며 다섯 건 모두를 live causal E2E로 해석하면 안 된다.
- 현재 R1 10건 중 대표 3건은 Human Review `PENDING`까지만 준비했다. 사람 계정으로 Resolve하기
  전에는 Decision·Review Report·Resolution·DRY-RUN을 만들지 않으며, 이번 세션에서도 생성 수는 0이다.
- canonical Rule Set `2.0.1`은 DB 재구성 순서와 동일한 rule/source 정렬을 강제한다. 기존 faulty
  `2.0.0`과 그 실패 Evaluation/Outbox는 삭제하지 않고 RETIRED 감사 이력으로 남겼다.
- 정책 입력 snapshot은 실제 Vision과 미연결인데도 `MOCK_QUALIFIED`로 기록되는 provenance 정밀도
  한계가 남아 있다. 또한 `case.order_amount`는 generic attributes 기반이므로 실제 입력 확장 전
  source-tagged typed schema로 분리해야 한다. 현재 R1 seed는 이 값을 제공하지 않는다.
- `분석 계속하기` 422는 Case의 UTC 날짜 `2026-08-27`을 그대로 보내면 KST
  `2026-08-28`부터 효력인 Rule Set `2.0.1`이 선택되지 않던 문제였다. 현재 Web은
  가상 한국 데모의 업무 시간대 `Asia/Seoul`로 기준일을 계산한다. 다중 지역·실제 Tenant
  적용 전에는 서버가 권위 있는 Tenant timezone/policy-date 계약을 제공해야 한다.
- UI·API 수정과 자동 회귀는 통과했지만 Web rebuild로 기존 브라우저 memory token이
  초기화되어 인증된 R1 Case에서 수정된 CTA를 직접 클릭하는 마지막 수동 확인은 남아 있다.
  로그인 후 기존 실패 Case에서 재시도하면 추가 결정 없이 확인할 수 있다.
- HDP-100 기능은 `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d`, closeout은
  `5c152fd0d1e97eba3b41b2ecea1cff7811814d90`로 Commit했고 local HEAD와 동일 원격 기능
  브랜치 SHA를 확인했다. PR 생성과 `develop` 병합은 아직 실행하지 않았다.
- GitHub에는 장기 `poc`, `mvp`, `final` branch가 따로 없다. 경량 GitFlow 계약상 현재 PoC는
  `feature/scenario-poc-hard-plastic`, 다음 통합/MVP 후보는 `develop`, 배포 가능한 최종 기준은
  `main`이다. 별도 영구 `mvp/final` branch를 추가하기보다 검증된 feature PR→`develop`,
  안정화 `release/vX.Y.Z`→`main`, annotated tag 순서를 따라야 한다.
- 원격 PoC는 `81b6e20`까지 fast-forward했고 CI #108이 PASS했다. 실제 E3 runtime·Top-100/정상 참고
  replay·현실형 10건·가상 정책 `2.0.1`은 `0f4de4b`, 상담원 UI·422 복구·빠른 검토·환불 확인서는
  `b3e09cf`, handoff는 `81b6e20`이다. 사용자 소유 문서 3개는 계속 미추적 보존한다.
- Vision 담당 원격 `feature/3-kaputt-dinov2-training`은 공통 기준 `4037d73`에서 PoC와 갈라져
  Vision 쪽 55 commits, PoC 쪽 21 commits가 서로 독점이다. Draft PR #4와 latest CI는 PASS지만
  PoC branch에 직접 merge하면 status/doc 및 runtime 계약 충돌 검토가 필요하다.

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
- Sprint 3 Vision Stage의 원래 Closeout은 Mock-qualified였다. 이후 E3 server/model/threshold
  runtime 연결은 통과했지만 실제 제품 dataset과 제품별 calibration은 여전히 검증하지 않았다.
- Text/Vision Alignment와 Claim↔Detection matching은 구현하지 않았다. Review UI와 immutable
  Review Report는 Sprint 5C 내부 데모로 구현됐지만 실제 운영 사용자/정책/데이터 품질 증거는
  없다. Policy Engine은 typed guidance만 생성하고 최종 업무 결정은 계속 Human Review가
  소유한다. Case/Evidence 접수만으로 Analysis가 자동 시작되지 않는다.
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
- Sprint 4B Policy Corpus/Gold는 전부 합성 Reference이며 실제 기업 정책 정확성·법률 효력과
  실제 사용자 query 분포는 검증하지 않았다. Baseline corpus는 168 clause 규모다.
- Retrieval Test 40은 frozen profile로 한 번 실행 완료했다. Local MLX Query Builder와
  Grounded Explanation은 별도 Local PoC로 평가됐지만 Production Target Qwen3.8 재평가가 남았다.
  Policy Engine→Human Review→Resolution은 구현됐지만 실제 외부 실행과 운영 routing은 없다.
- Mac MPS embedding은 qualified지만 서비스 요청은 lock으로 직렬화되며 concurrency 2와 장시간
  swap/thrashing은 측정하지 않았다. Production network/process supervisor는 후속 운영 범위다.
- Qwen reranker는 Mac MPS에서 실제 qualification했지만 단일 process lock과 concurrency 1로
  제한한다. CPU fallback, 장시간 안정성, 실제 사용자 query 분포, production supervisor는 미검증이다.
- Locked Test에서 reranker는 Recall@10을 높이지 못했고 MRR/nDCG도 개선하지 못했다. 따라서
  자동 활성화 확대나 파라미터 재튜닝을 하지 않고 `RERANKER_NO_MEASURABLE_GAIN`으로 보존한다.
- 후보 K20 이후 recall 이득이 없고 candidate recall 0.9375가 현 corpus/query의 절대 상한이다.
  Query Builder 평가와 corpus recall 개선을 reranker 재튜닝보다 먼저 수행해야 한다.
- Sprint 4C-2의 실제 LLM Query Builder 3-way qualification은 계속
  `BLOCKED_EXTERNAL_LLM`이다. 4C-3A는 선택된 RAW 검색 결과와 독립적으로 진행했으며 이를
  LLM Query Builder 품질 증거로 해석하지 않는다.
- Sprint 4C-3A 구조 검증 뒤 Local MLX Grounding 의미 평가를 작은 합성 Test 10건과 사람
  spot-check 10건에서 통과했지만, 이를 Production faithfulness나 실제 기업 정책 품질로
  확대 해석하지 않는다.
- Citation Pack은 합성 Reference corpus의 immutable snapshot이다. 실제 기업 정책 정확성,
  법률 효력, 실제 사용자 분포, 보관·삭제 정책은 검증하지 않았다.
- 빠른 검토 `0.70`은 모델 confidence, Vision threshold, 정책 정확도 또는 실제 위험 확률이 아니다.
  `REQUIRES_HUMAN_REVIEW` 0.35, immutable Rule 0.25, Citation 0.15, qualification metadata 0.10,
  단일 `MARK_REVIEW_ELIGIBILITY` mapping 0.15의 PoC workflow-readiness 합계다. 제품 적용 전에는
  실제 상담원 사용성·오판 비용·Shadow 비교로 별도 재설정해야 한다.
- `허용`은 immutable Packet에서 `RETURN/REFUND/EXCHANGE/RESHIPMENT/REPAIR_REVIEW` 중 하나의
  typed mapping이 확정될 때만 활성화된다. `OTHER`, `ACTION_REVIEW`, 충돌 mapping은 고객 문장이나
  모델 출력으로 추론하지 않고 상세 검토로 보낸다. `비허용`은 준비도 Gate 통과 시
  `REJECT_REQUEST`로 기록한다.
- 빠른 검토는 사람이 누르는 하나의 UI 동작으로 기존 Claim·Resolve API를 조합한다. 자동화 테스트에서
  Decision→Resolution→Report를 검증했지만 실제 대기 중 R1 Case는 사용자 판단을 대신하지 않기 위해
  이번 세션에서 클릭하지 않았다. 따라서 live DB의 해당 Decision 생성은 다음 사용자 조작으로 남는다.
- 환불 처리 확인서는 Shopify·Stripe와 국내 전자상거래 공식 자료의 공통 필드를 참고한 CSight 가상
  사내 양식이다. 실제 결제업자 취소, 고객 통지, RMA·추적번호, 법정 처리기한을 기록한 증빙이 아니며,
  외부 연동 전에는 해당 항목을 `미요청/미발송/미연동`으로 유지한다. `ACTION_DRY_RUN_VALIDATED`도
  `환불 완료`가 아니라 `환불 요청 검증 완료`로만 표시한다.
- 메모리 약 4.21 GiB는 idle/ready 단일 시점 귀속 합계다. Apple MPS는 일반 RSS 대신 physical
  footprint를 사용했고 Docker는 cgroup 값을 사용했으므로 공유 page/cache 때문에 시스템 전체 사용량과
  정확히 일치하지 않는다. Vision peak 2,935 MiB와 Embedding peak 1,767 MiB는 동시 peak가 아니다.

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
- [x] 실제 E3 endpoint와 immutable model/taxonomy/threshold를 연결하고 synthetic image로
  direct HTTP와 Core causal model Gate를 실행한다.
- [ ] 제품도메인 대표 이미지와 Human Gold를 고정한 뒤 별도 product qualification을 실행한다.
- [x] 4090 Node의 Kaputt 전체 Query 추출 상태와 `plastic_hard` 분포를 확인하고, 별도 Qwen3.8
  VLM의 append-only 구조화 표본 4건을 실행한다.
- [x] `plastic_hard` 표본 4건의 Query/Reference Crop을 선택 추출해 사진 2장+비교 Prompt로
  재실행하고 상품 유형·가시 근거·defect-positive 탐지를 사람 검수한다.
- [x] paired 30건에서 결함 비교와 상품 메타데이터 schema/prompt를 분리하고 specific name 비율,
  금지 필드, 민감 패턴, latency와 결함 confusion/coverage를 평가한다.
- [ ] 사람이 paired 30건의 일반 상품명·category를 Gold로 확정하고 supplement,
  cleaning/chemical, pet-care taxonomy를 결정한 뒤 Qwen 후보의 accuracy를 계산한다. 결함 Target은
  공식 Label/E3만 사용한다.
- [ ] 다음 기능 Sprint에서는 먼저 Evidence Alignment 입력 계약과 Claim↔Detection matching,
  confidence calibration을 설계하고 Policy/Approval을 계속 분리한다.
- [ ] Evidence Reconciliation·Orphan Cleanup·업로드 Idempotency와 Retention 정책을
  우선순위에 따라 별도 작업으로 계획한다.
- [x] Sprint 3 Closeout Commit을 확인하고 `feature/sprint-4a-llm-reference-data`에서 LLM
  Contract v2와 합성 Reference Data를 구현한다.
- [x] Sprint 3 Closeout Commit `330cbdb`와 Sprint 4A 전용 Branch를 확인한다.
- [x] LLM Contract v2, 합성 Policy Corpus와 고정 Evaluation Dataset을 구현한다.
- [x] Sprint 4A 최종 Gate를 확정하고 미커밋 상태로 인계한다.
- [x] Sprint 4B Policy ingestion→BM25→Qwen embedding→exact pgvector→RRF→locked evaluation을
  완료한다.
- [x] Sprint 4C-1은 frozen candidate baseline을 변경하지 않고 Qwen3-Reranker-0.6B profile,
  candidate reranking과 locked evaluation을 완료한다.
- [x] Sprint 4C-2에서 negative reranker 결과를 고정하고 raw/deterministic/LLM query builder를
  동일 candidate/evaluation 계약으로 분리 비교한다.
- [x] Citation Pack, strict grounded explanation schema, deterministic citation validation과
  Mock E2E를 Sprint 4C-3A 별도 계약으로 연결한다.
- [x] Sprint 4C-3A를 독립 감사하고 최신 Docker·Broker Gate까지 재통과한다.
- [x] 승인된 4C-3A 범위만 `feat: add citation grounding guardrails`로 로컬 Commit하고 새
  `feature/sprint-4c3b-local-mlx-grounding` 브랜치를 생성한다.
- [x] Local MLX Endpoint로 Grounding Dev 40 + Injection Dev 20에서 4C-3B를
  qualification하고 prompt/profile freeze 뒤 sealed Test 각 10건을 한 번만 실행한다.
- [x] Local MLX로 semantic citation precision/recall, unsupported policy claim rate와
  paraphrase faithfulness를 측정하기 전에는 구조 통과를 의미 품질 통과로 승격하지 않는다.
- [x] Sprint 5A에서 versioned Policy Engine Core를 구현하고 Grounded Explanation과 최종
  결정을 분리한다.
- [x] Sprint 5B Human Review decision record와 Admin override 계약을 구현한다.
- [x] Sprint 5B를 `4aefae6 feat: add human review workflow`로 Commit하고 원격 기능 브랜치에 백업한다.
- [x] Sprint 5C Resolution·External Action DRY-RUN, Review Report·KPI와 React 상담원 UI를 구현한다.
- [x] Sprint 5C 최종 Diff를 검토하고 `0a5f529` 기능 Commit·closeout 원장을 원격 기능 브랜치에 백업한다. PR과
  `develop` 병합은 거버넌스 결정 전까지 보류한다.
- [x] parallel Text/Vision join race 수정본을 live Mock binary 경로에서 재실행하고 terminal
  Run/Stage/Result/Assessment row와 duplicate 결과를 인과적으로 확인한다.
- [x] 재검증이 끝난 뒤에만 HDP-100 branch의 static/default/integration/migration/runtime 정확한
  수치를 새 원장 행에 추가한다. 기존 Sprint 5C 554/51 수치는 덮어쓰지 않는다.
- [x] HDP-100 변경을 `dfd6db2 feat: add hard-plastic scenario PoC`로 Commit하고 동일 원격 기능
  브랜치 SHA를 확인한다. PR과 `develop` 병합은 별도 결정 전까지 보류한다.
- [x] 실제 E3 checkpoint와 host-private endpoint를 확보하고 model identity, threshold,
  direct inference와 Core 저장 경로를 검증한다.
- [x] safe stop·idempotent setup·restart 뒤 direct score 재현과 Docker Worker health를 확인한다.
- [x] 전달받은 selected-correct Top-100의 파일 무결성을 검증하고 실제 E3 100장 전수 replay와
  비식별 hard-plastic 6건의 local Core causal sample을 수행한다.
- [x] 사용자 제공 정상 참고 77장을 격리 감사·실제 E3 replay하고, 결함 후보 6·threshold 미만 참고
  4의 현실형 내부 데모 Case/Evidence 10건을 비공개 저장 경로에 고정한다.
- [x] `csight` fictional 정책 Runtime을 local-only fail-closed로 준비하고 대표 결함 1·기준 미만 1을
  Text v2→RAW Top-3→Grounding→Policy→Human Review `PENDING`까지 실제 실행한다.
- [x] R1 장문 문의 10건·3열 상담원 UI·CSight Commerce 가상 정책 8문서/52조항과 canonical
  Rule Set `2.0.1`을 구현하고 대표 수리·Safety·단순변심 3건을 Human Review까지 실제 실행한다.
- [x] 검증된 R1 사진 10장에 표시 전용 가상 상품명·SKU·KRW 가격대·문의 목적을 매핑하고
  Case 목록 검색/표시와 상세 상품 카드에서 실제 판매가·환불 입력이 아님을 명시한다.
- [x] `COMMERCE_CONTEXT_R2_E3` 10건에 합성 고객 ID/이름·마스킹 연락처·주문/결제·가상 배송지와
  운송 정보를 DB 저장하고, Case 목록/상세와 새 환불 확인서 스냅샷에 allowlist로 연결한다.
- [ ] 추가 사진 시나리오는 개인 이름·바코드·브랜드·중복을 제외하고 사진별 제품군과 SHA를
  검토한 뒤 별도 버전으로 확장한다. 같은 사진에 다른 상품을 임의로 중복 매핑하지 않는다.
- [x] Case Workspace를 `지금 할 일` 단일 CTA와 2열 본문으로 단순화하고,
  데스크톱 inert X를 제거하며 UTC/KST policy-date 422와 API 오류 메시지 파싱을 수정한다.
- [x] Review 화면에 PoC 준비도 0.70 기반 `허용/비허용` 빠른 검토를 추가하고, 인증 Human 클릭 뒤
  CAS Claim→Resolve→Resolution/DRY-RUN→immutable Review Report 자동 열기를 연결한다.
- [x] `APPROVE_REFUND` 보고서를 금액·수량·처리 상태·취소 요청·고객 통지·반품 추적·정책 승인·
  감사 ID가 포함된 `환불 처리 확인서`로 분리하고 A4 인쇄, 누락값 fail-closed, 실제 환불 미실행
  표기를 검증한다.
- [x] 내부 decision/status 코드를 자연어 업무 라벨로 표시하고 terminal Report에서 고객 안내 EMAIL
  simulation을 생성·재열람하되 `SIMULATED_NOT_SENT`와 side effects 0을 고정한다.
- [x] terminal Report와 같은 transaction에서 tenant별 비식별 학습 asset을 자동 적재하고, 기존
  Report를 소급 allowlist 적재하며 데이터 자산 화면에 30/60건 기준선 준비 상태를 표시한다.
- [ ] 실제 상담원 처리 표본이 30건에 도달하면 데이터 누락·분포·버전 구성을 검토해 기준선을 승인하고,
  60건 전에는 드리프트 비교 수치를 생성하지 않는다.
- [ ] 인증된 담당자가 대기 중인 비Safety 대표 Case 하나에서 실제 `허용` 또는 `비허용`을 선택하고,
  생성된 Decision·Resolution·Report를 확인한다. 이 선택은 변경 불가능한 사람의 최종 판단이다.
- [ ] 로그인한 상담원 세션에서 기존 422 Case의 `분석 계속하기`를 한 번 누르고
  Policy `2.0.1` 성공 또는 이전 성공 실행 복구를 확인한다.
- [ ] 상담원 콘솔에서 대기 중인 대표 3건을 인증된 사람이 검토한다. 실제 판단이 입력되기 전에는
  Resolve·Review Report·Resolution·DRY-RUN을 만들지 않는다.
- [ ] 실제 데이터 입력 전에 Policy input qualification과 금액 provenance를 source-tagged typed
  schema로 보강한다.
- [ ] HDP-100 5개 합성 시나리오의 대표 이미지셋·Human Gold·재현 점수를 버전 고정한다.
- [ ] E3 endpoint timeout/restart와 malformed response를 live 주입하고 retry/fail-closed를 검증한다.
- [x] `doongdoong.org`·`www` Cloudflare ingress를 지뢰찾기 3000/3001에서 CSight Web 8080으로
  전환하고 외부 Web·API·Admin 인증과 브라우저 Login 화면을 검증한다.
- [x] GitHub 조직 저장소의 원격 branch·PR·CI·tag와 로컬 worktree를 교차 감사하고
  PoC=`feature/scenario-poc-hard-plastic`, MVP 통합=`develop`, 최종 릴리스=`main` 역할을 확인한다.
- [x] 로컬 후속 변경을 E3 runtime, 현실형 demo/policy, 상담원 Web, 상태 문서의 검토 가능한
  Commit으로 분리하되 사용자 소유 문서·raw image·checkpoint·local report는 제외한다.
- [x] 분리 Commit 전체 회귀와 Secret/대용량 파일 감사를 통과하고 사용자의 승인 범위에서
  원격 PoC branch를 fast-forward로 최신화해 CI #108 성공을 확인한다.
- [ ] Vision Draft PR #4의 `ml/cv` 변경을 현재 PoC runtime 계약과 별도 비교해 충돌을 해결한 뒤
  `develop` 통합 순서를 결정한다. PoC PR과 PR #2/보호 규칙 결정 전 `main` 승격은 금지한다.
- [ ] 공개 터널을 공유하기 전 Cloudflare Access를 적용하거나 `csight` Admin Credential을
  강화하고, 시연 종료 뒤 터널 복원·중단 여부를 결정한다.
- [ ] Kaputt 권리 범위를 벗어나는 고객·상업 사용은 별도 법률·권리자 승인 전 차단한다.
- [x] 내부 PoC 상품군 4개·결함군 3개와 첫 10건 SHA Allowlist를 버전 고정하고, E3 점수 margin과
  source label·사람 승인 fail-closed Gate를 적용한다.
- [x] 별도 `poc_closed_set/2.0.0`에 새 10건을 승인해 식품·건강보조제와 생활화학·접착제를 포함한
  상품군 4/4를 표현하고 actual E3·멱등 재실행을 통과한다. 이는 Human Gold 성능평가가 아니다.
- [ ] 고객 후보, 상품군 1개, 결함 유형 2~3개와 비식별 실제 Case/Human Gold 30건 이상을 확보한다.
- [ ] 버전·효력일이 있는 실제 기업 정책과 실제 Policy/Case/User Query 분포 평가를 확보한다.
- [ ] Retention·삭제·EXIF 제거·접근권한 승인을 받고 증거 artifact ID/hash를 Gate에 연결한다.
- [x] E3 manifest·preprocess·threshold·labels·model card와 checkpoint SHA package를 고정한다.
- [ ] 제품별 결함 평가를 완료하거나 Vision의 제품 적용 제외 범위를 명시 승인한다.
- [ ] 실제 목표 분포에서 Qwen3.8 Extraction·Grounding을 재평가하고 Shadow Mode Human 비교를 완료한다.
- [ ] 모든 외부 증거와 zero-safety/clean-environment artifact가 갖춰진 뒤에만
  `make require-limited-poc`으로 `LIMITED_POC` 승격을 판정한다.
- [ ] 대표 10 Case를 연속 처리하면서 5초 간격으로 Vision·Embedding physical footprint, Docker
  container memory, queue depth와 실패율을 함께 기록하고 p95/peak 기준점을 추가한다.

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

### 2026-08-26 — Sprint 4B Policy Corpus Ingestion과 Hybrid Retrieval

- Git: Sprint 4A를 `6f3a667 feat: add LLM contract v2 and policy reference corpus`로 로컬
  Commit하고 `feature/sprint-4b-policy-retrieval` 생성; Sprint 4B Commit·Push·PR 없음
- Persistence: `20260826_0006`, manifest-driven immutable ingestion, tenant 2/document 24/clause
  168/embedding 168, idempotent run reuse와 version content mismatch 차단
- Retrieval: `ko_policy_lexical:1.0.0` exact BM25, pinned Qwen3 1024-d last-token normalized
  embedding, metadata-filtered pgvector exact cosine, weighted `policy_rrf:1.0.0`
- API: JWT principal tenant 기반 read-only 세 mode; 두 tenant 6 smoke 통과. Provider down에서
  lexical 200, dense/hybrid 503, Core readiness 200
- Evaluation: Dev 80에서 BM25/RRF freeze 후 Test 40 한 번 실행. Cross-tenant, future, retired,
  wrong-version, hard-negative, duplicate 0; determinism 100%
- Qualification: Apple M4/32 GB/macOS/MPS에서 model load와 168-clause embedding 실제 측정,
  external embedding Skip 0. Process supervisor/concurrency 2는 미검증
- 검증: Ruff/Format/Pyright, Fast, Unit/Contract/Architecture/API, 전체 Integration, migration
  3경로/drift 0, 최신 Core 6개 Healthy. 정확한 최종 count는 같은 날짜 검증 원장 최신 행 참조
- 실패 기록: 첫 embedding DB build FK flush, 첫 API image의 dev-only dependency, Dev result directory,
  도구 background process 수명주기 실패를 수정·재검증하고 숨기지 않음
- 문서: ADR-0026~0038, RAG guide 4개, Qwen manifest, 설계 03~10, README와 Sprint 4B progress
- 안전: `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- 다음 작업: Sprint 4C에서 reranker를 먼저 독립 qualification하고 그 뒤 query builder/citation/
  grounded explanation을 별도 locked evaluation으로 진행

### 2026-08-26 — Sprint 4B 독립 Closeout 감사

- 목표: 미커밋 Sprint 4B 전체 Diff를 코드·DB·평가 artifact·실서비스 기준으로 재감사하고
  로컬 기준점 Commit 조건을 확정
- 판정: P0 0, P1 0, `SPRINT_4B_CLOSEOUT=PASS`
- 검증: Ruff, Format 210, Pyright 0, Fast 376/48 deselected, Unit 306,
  Architecture 6, Contract 58/1 deselected, E2E 6, Integration 41/외부 GPU 5 skipped
- 데이터: tenant 2/document 24/clause 168/embedding 168/ACTIVE index 2, 동일 ingestion run
  재사용, parent/dimension mismatch 0
- 실제 모델/API: Qwen embedding MPS, external 1/423 deselected, 두 tenant 세 mode smoke,
  provider down LEXICAL 200·DENSE/HYBRID 503·Core ready 200
- Migration/Runtime: empty/previous/round-trip 세 경로 `0006`, drift 0, 임시 DB 정리,
  Core 6개 Healthy
- 문서 공백: 요청된 `PROJECT_BLUEPRINT.md`는 저장소에 없으며 canonical 설계 문서는
  `CSight_project_docs/docs`에서 감사
- 안전: 사용자 `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage
- 다음 작업: 승인된 Sprint 4B 범위만 `feat: add hybrid policy retrieval baseline`으로 로컬
  Commit하고 Push/PR 없이 Sprint 4C-1 브랜치를 생성

### 2026-08-26 — Sprint 4C-1 Qwen Policy Reranker Qualification

- Git: Sprint 4B를 `4216028 feat: add hybrid policy retrieval baseline`으로 로컬 Commit하고
  `feature/sprint-4c1-policy-reranker` 생성; Sprint 4C-1 Commit·Stage·Push·PR 없음
- Candidate: frozen HYBRID_RRF를 K10/20/30/50으로 분석해 Dev max recall의 최소 K20과 final10을
  선택. Test 후보 진단은 한 번만 실행했고 K20 recall 0.9375, oracle nDCG 0.95164
- Model: `Qwen/Qwen3-Reranker-0.6B` revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`,
  MPS private service, pair serialization 1.0.0, normalized yes/no score를 실제 검증
- Qualification: token min/p50/p95/max 172/178/187/189, truncation 0, cold load 3.60초,
  K20 p50/p95 2.362/2.375초. concurrency 2에서 tokenizer race를 수정했지만 처리 이득이 없어
  운영 동시성은 1로 제한; `QWEN3_RERANKER_QUALIFIED_WITH_LIMITATIONS`
- Architecture: 기술 독립 Port/Profile, Remote/Mock Adapter, full candidate allowlist와 응답 검증,
  `HYBRID_RERANKED`, no fallback, provider-down 503, 기존 세 mode와 Core readiness 보존
- Persistence: `20260826_0007`, immutable reranker profile과 tenant별 ACTIVE execution profile;
  activation 2회가 profile 1/execution 2를 유지
- Evaluation: Dev 80 freeze 뒤 locked Test 40 한 번. Test Hybrid→Reranked Recall@10
  0.925→0.925, MRR 0.53833→0.51250, nDCG 0.59841→0.59802; 개선 17/악화 23
- Correctness: cross-tenant/wrong-version/future/retired/duplicate/hard-negative/candidate mutation 0,
  Dev deterministic rerun 100%; Test 재호출·재튜닝 없음
- 검증: Ruff, Format 232, Pyright 0, Fast 402, Unit 319, Architecture 8, Contract 69,
  E2E 6, Integration 42, External embedding/reranker 각 1, Migration 세 경로 drift 0,
  두 tenant API와 Core 6개 Healthy
- 판정: `RERANKER_NO_MEASURABLE_GAIN`. 다음 작업은 Sprint 4C-2에서 negative result를 보존하고
  raw/deterministic/LLM query builder를 분리 평가하는 것
- 안전: `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage

### 2026-08-27 — Sprint 4C-1 독립 Closeout 감사

- 목표: Sprint 4C-1 전체 Diff를 candidate/oracle, model contract, API, DB, 외부 MPS와
  locked evaluation 기준으로 독립 재감사하고 로컬 기준점 조건 확정
- 발견·수정: `make format-check`가 `infra/reranker`를 검사하지 않던 P1 1건을 전체 `infra`로
  확장; P0 0, 수정 후 P1 0
- 검증: Ruff, Format 234, Pyright 0, Fast 402, Unit 319, Architecture 8, Contract 69,
  E2E 6, Integration 42, External embedding/reranker 각 1
- Evaluation: K20/final10, candidate recall 0.9375, mutation 0, Dev 80 재계산 mismatch 0,
  Test 재호출 없음; `RERANKER_NO_MEASURABLE_GAIN` 유지
- Failure record: 봉인된 Dev artifact를 생성 명령으로 덮어쓰려는 시도는 guard가 거부했고,
  전용 verifier로 재현성을 확인. Make background model은 도구 셸 수명 때문에 종료돼 foreground
  세션으로 재실행
- Migration/Runtime: empty/previous/round-trip `0007`, drift 0, 임시 DB 정리, Core 6개 Healthy,
  base mode 200/reranked provider-down 503/readiness 200
- 안전: Push·PR 없음, `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- 다음 작업: 승인된 Sprint 4C-1 범위만 `chore: qualify qwen3 policy reranker`로 로컬 Commit하고
  `feature/sprint-4c2-policy-query-builder` Branch 생성

### 2026-08-27 — Sprint 4C-2 Policy Query Builder

- Git: 4C-1을 `14cae29 chore: qualify qwen3 policy reranker`로 로컬 Commit하고
  `feature/sprint-4c2-policy-query-builder` 생성; 4C-2 Commit·Push·PR 없음
- External: 실제 Endpoint 부재로 Extraction v2와 LLM Query Builder를
  `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`로 기록; Mock을 Qwen 성능으로 사용하지 않음
- Dataset: 새 `policy_query_builder_v1` Dev 80/Test 40, Test sealed, broken/cross-tenant 0,
  hash `5040f219aff5546a88073f132889215df2574c3196bdcad9f4f9e28141fd72c4`
- Contract/Retrieval: Strict 1~3 Query, deterministic 1.0.0, prompt 1.1.0, Core hard filters,
  frozen HYBRID K20, reranker off, `policy_multi_query_rrf:1.0.0`, query provenance
- Persistence/API: Migration `0008`, append-only Run/Profile/Query/Hit와 전용 Outbox, POST 202/
  replay 200/conflict 409, List/Get, Viewer read-only, v1 result 거부
- Live: deterministic와 Mock-LLM Run SUCCEEDED, duplicate task NOOP, provider-down은
  `POLICY_QUERY_BUILDER_PROVIDER_UNAVAILABLE`, embedding-down은 `EMBEDDING_PROVIDER_UNAVAILABLE`,
  Core readiness 200, cross-tenant detail 404
- Evaluation: Dev RAW Recall/MRR/nDCG 1.0/0.709549/0.724277, deterministic
  1.0/0.667133/0.636635. Freeze 뒤 Test 1회 RAW 0.975/0.739236/0.741392,
  deterministic 1.0/0.724544/0.657571
- 판정: 평가된 두 전략에서는 RAW를 선택했지만 실제 LLM 비교가 없어 최종은
  `BLOCKED_EXTERNAL_LLM`; 기본 Retriever HYBRID 유지
- 검증: Ruff/Format 252/Pyright 0, Fast 419, Unit 327, Architecture 8, Contract 78,
  E2E 6, Integration 42/5 skipped, External embedding 1, Migration 3경로 drift 0,
  Core 6 healthy, 실제 RabbitMQ Worker vertical slice PASS, `git diff --check` PASS
- 다음 작업: 승인된 Qwen Endpoint가 생기면 Dev qualification부터 수행하고, 이후 4C-3
  Citation Pack/Grounded Explanation gate로 진행

### 2026-08-27 — Sprint 4C-2 Closeout and Sprint 4C-3A Citation Grounding

- Git: 4C-2를 `a282817 feat: add case-based policy retrieval query planning`으로 로컬
  Commit하고 `feature/sprint-4c3a-citation-grounding-guards` 생성; Push·PR 없음
- Citation Pack: 성공 Retrieval Run의 rank, clause/document version, title/section/type/text,
  effective interval, source hash, query IDs/strategy와 retrieval profile hash를 immutable snapshot
- Contract: 고정 중립 summary, statement별 citation 필수, extra field 금지, unresolved condition만
  허용; approval/rejection/fraud/responsibility/liability/final decision field 부재
- Validation: pack-local `CIT-NNN` allowlist, duplicate normalization, ACTIVE/as-of/version/tenant
  recheck, unknown citation fail-closed; Raw prompt/response/reasoning 비저장
- Async/API: append-only profile/pack/item/run/result/outbox, identifier-only RabbitMQ payload,
  thin Celery Worker, Case 하위 POST/List/Get, tenant isolation
- Evaluation: 합성 Grounding 50 + Injection 30에서 structural violation 0, replay 100%; semantic
  citation precision/recall, unsupported claim, paraphrase faithfulness는 실제 Qwen 부재로 SKIPPED
- Verification: Format 258/Ruff/Pyright PASS, Fast 431 passed/3 external skipped,
  Integration 42 passed/5 external GPU skipped, Grounding 대상 12 passed
- Migration/Runtime: empty/previous/round-trip `0009`와 drift 0; 실제 PostgreSQL/RabbitMQ/Celery
  Mock에서 10 citation/statement, replay 200, tenant 404. Provider-down은 stable unavailable로
  종료하고 result·Mock fallback 0; 검증 행 정리 완료
- Runtime audit fix: Compose 기본 Worker queue 목록에 `grounded-explanation`을 추가하고 rendered
  config에서 소비 대상 포함을 확인
- Docker: 외부 registry metadata 응답 정지로 새 image rebuild는 BLOCKED. Dockerfile diff 0,
  기존 Core 6개는 Healthy/live·ready 200이며 host-native 4C-3A broker flow로 런타임 검증
- 다음 작업: 4C-3A를 미커밋·Push/PR 없음으로 인계하고, 실제 Qwen 사용 가능 시 4C-3B Dev
  qualification부터 수행. Registry 복구 후 Docker image rebuild 재검증

### 2026-08-27 — Sprint 4C-3A Independent Closeout

- Audit: Citation Pack snapshot/allowlist, decision-free strict schema, append-only persistence,
  identifier-only broker payload와 thin Worker를 실제 코드·DB·API·Broker 기준으로 재검토
- 판정: P0 0, P1 0, `APPLICATION_QUALIFICATION=PASS`; semantic citation 품질은 실제 모델
  평가 전이므로 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` 유지
- Regression: Format 258, Ruff 0, Pyright 0, Fast 431 passed/3 skipped/47 deselected,
  Architecture+Unit+Contract+E2E 431 passed/2 skipped, Integration 42 passed/5 skipped
- Migration: empty/previous/round-trip `0009`, drift 0, 임시 DB 3개 정리
- Docker recovery: 제한적 재시도에서 최신 image build 성공; Dockerfile diff 0, Core 6 healthy,
  live/ready 200, 4 queues consumer 1·depth 0
- Live: 10 citations/statements, replay 200, tenant 404; terminal event 2회 재전달 뒤 run/result
  각 1건; provider-down은 stable unavailable, result 0, Mock fallback 0
- Cleanup: 검증용 Grounding run/result/outbox/item/pack을 범위 한정 삭제하고 대상 run 0 확인
- Git: `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음; Closeout Commit만 생성하고
  Push·PR은 하지 않음
- 다음 작업: 지정 Commit에서 `feature/sprint-4c3b-local-mlx-grounding`을 만들고 preferred
  MLX artifact 존재성·revision·호환성을 먼저 검증한 뒤 Dev→freeze→Test 순서로 진행

### 2026-08-27 — Sprint 4C-3B Local MLX PoC

- Git: 4C-3A를 `72cbe12 feat: add citation grounding guardrails`로 로컬 Commit하고
  `feature/sprint-4c3b-local-mlx-grounding` 생성; 4C-3B Commit·Push·PR 없음
- Runtime: exact `mlx-community/Qwen3.5-9B-MLX-4bit` revision
  `938d8919941c6e7efd3c7150eff7fe9d12afa631`, MLX 0.32.2/mlx-vlm 0.6.17,
  localhost:8080, 4096 context, 512 output, concurrency 1, thinking disabled
- Extraction: Dev120/Test40 구조·source quote 100%, Test issue/action/ambiguity F1
  0.8533/0.1935/0.1951; `LOCAL_POC` only
- Query: Dev80/Test40 구조·안전 100%. Test Local Recall@10 0.90와 coverage 0.75가 RAW
  0.975/0.85보다 낮아 `RAW_REMAINS_SELECTED`
- Grounding: Dev40/Test10, Injection Dev20/Test10 구조·citation·의미·replay 100%, 위반 0;
  사람 spot-check Dev20/Test10 모두 rubric PASS
- Live: Docker Core 최신 rebuild 성공, 6개 healthy. Docker Worker→Mac MLX 실제 safe-default
  top-3 E2E 10/10, duplicate 0, citation violation 0. top-10은 4096 context 초과로 fail-closed
- Stability: 2시간 34분 이상 연속, RSS 약 6.50 GB, swap 0
- 미완료: 실제 timeout→recovery와 malformed-provider fault injection은 미실행(offline contract만
  존재). Qwen3.8 Production Target 재qualification 필요
- 검증: Ruff/Format/Pyright PASS, Default 437 passed, Architecture+Unit+Contract+E2E 437 passed,
  Integration 42 passed/5 skipped, External Local MLX 3 passed/skip 0, Migration drift 0,
  `git diff --check` PASS, 실제 Local 결과 cross-tenant 404
- 장애: unreachable Local endpoint는 retryable `LLM_PROVIDER_UNAVAILABLE`/provider `mlx`, Core
  readiness 200, Mock fallback 0. 실제 timeout recovery와 malformed response injection은 미실행
- Git 인계: Sprint 4C-3B 변경은 요청대로 미커밋; `kaputt_best_vision_architecture.md`는
  미수정·미삭제·미Stage
- 다음 작업: 실제 timeout recovery/malformed provider fault injection, Qwen3.8 재qualification,
  Sprint 5A Policy Engine과 Human Review Gate 준비

### 2026-08-27 — Sprint 4C-3B Independent Closeout

- 판정: P0 0, P1 0, `SPRINT_4C3B_CLOSEOUT=PASS`; 범위는 Local PoC이며 Qwen3.8 Production
  qualification이나 실제 기업 정책 품질을 의미하지 않음
- Runtime: pinned Qwen3.5-9B MLX revision, MLX 0.32.2/mlx-vlm 0.6.17, strict JSON과 reasoning
  leakage 0을 재확인; 실제 unreachable endpoint는 retryable provider `mlx`, Core ready 200
- Regression: Ruff 0, Format 275, Pyright 0, Default 437 passed/53 deselected,
  Integration 42 passed/5 external-GPU skipped, External Local MLX 3 passed/487 deselected
- Artifact: 봉인 Test를 재실행하지 않고 Extraction 40, Query 40, Grounding 10, Injection 10의
  metric/count와 frozen profile·현재 code prompt hash를 검증; Test 재실행 guard 확인
- 선택 결과: Extraction issue/action/ambiguity F1 0.8533/0.1935/0.1951, Local Query
  Recall@10 0.90 대 RAW 0.975로 `RAW_REMAINS_SELECTED`; 작은 합성 Grounding 결과를 Production
  faithfulness로 과장하지 않음
- Persistence/Runtime: head `20260827_0009`, drift 0, MLX extraction stage 12와 grounding result
  10, duplicate result group 0, raw prompt/response/reasoning column 0; Core 6 healthy, 4 application
  queue consumer 1/depth 0
- NOT_RUN: 실행 중 Local server의 ownership PID file이 없어 restart smoke는 안전상 미실행;
  실제 timeout→recovery와 malformed-provider runtime injection도 `OFFLINE_CONTRACT_ONLY` 유지
- Git: Closeout 문서 추가, `git diff --check` PASS. `kaputt_best_vision_architecture.md`는
  미수정·미삭제·미Stage; 정확한 로컬 Commit 메시지는
  `feat: add local MLX LLM grounding PoC`, Push·PR 금지
- 다음 작업: Closeout Commit 뒤 `feature/sprint-5a-policy-engine-core`를 생성하고, versioned
  deterministic Policy Engine을 LLM/RAG/최종 업무 결정과 분리해 구현

### 2026-08-27 — Sprint 5A Versioned Deterministic Policy Engine Core

- Git: Base `d0950f6`, Branch `feature/sprint-5a-policy-engine-core`; Sprint 5A 변경은 미커밋이며
  Push·PR 없음. 사용자 소유 `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage
- Core: versioned typed field/operator registry, five condition statuses, four rule statuses,
  deterministic aggregation과 final decision을 표현할 수 없는 six-effect allowlist 구현
- Safety: Local MLX action/ambiguity는 hard input에서 제외하고 Mock Vision 조건은
  `NOT_EVALUATED`; 불확실 조건은 자동 eligibility/exception을 만들지 않고 review/evidence로 수렴
- Data: synthetic tenant 2, immutable rule set 2, rule/source 24/24. 동일 version content conflict,
  cross-tenant/source-version/hash/effective mismatch를 fail-closed 처리
- Persistence: Migration `20260827_0010_policy_engine`의 10개 table, frozen typed input과
  qualification snapshot, append-only result/effect, identifier-only outbox를 구현
- Runtime: POST 202/replay 200/List/Get, exact queue identifiers, 전용 `policy-evaluation` route,
  thin Celery task, duplicate terminal delivery `NOOP`, viewer read-only와 tenant 404 확인
- Evaluation: Dev80 freeze 뒤 sealed Test40을 단 한 번 실행. selection/rule/condition/effect/
  summary/source/version/replay 모두 1.0, cross-tenant/future/retired/final-decision 위반 0;
  sealed Test 재실행 guard가 이후 호출을 거부함
- Verification: Ruff PASS, Format 296, Pyright 0, Default 456 passed, isolated Integration
  44 passed/5 external-GPU skipped, migration 세 경로와 live drift 0, rule DB audit PASS
- Runtime verification: 최종 Docker Core 6/6 healthy, five application queues consumer 1/depth 0,
  live smoke rules 12/replay 200/duplicate NOOP/tenant 404/Mock Vision `NOT_EVALUATED`
- Failure record: 첫 Integration 실행은 장기 Dispatcher가 test outbox를 먼저 claim해 1건
  실패했으며 서비스 격리 후 전체 통과. 첫 host Alembic 확인은 `.env` 미Export로 접속 전
  중단됐고 환경 적용 후 head `0010`/drift 0 확인
- 범위 밖: 실제 정책 타당성, 실제 Vision, Evidence Alignment, final decision, routing,
  Human Review UI/override/final report, rule editor와 LLM rule generation
- 다음 작업: 사용자 Diff 검토 후 명시적 승인 시 Sprint 5A 로컬 Commit만 생성한다. 이후
  Sprint 5B에서 Policy Effect를 append-only Human Review로 연결하되 최종 결정은 사람이 소유한다.

### 2026-08-27 — Sprint 5A Independent Closeout Audit

- 판정: P0 0, P1 0, `POLICY_ENGINE_CORE_QUALIFIED_WITH_LIMITATIONS`
- Integrity: deterministic rebuild hash 동일, ingest 신규 row 0, active/set/rule/source
  2/2/24/24, source·tenant·version·final-effect 위반 0
- Evaluation: Dev80만 재계산해 모든 metric 1.0과 위반 0 확인; 봉인 Test40은 verifier로만
  검증하고 재실행하지 않음
- Regression: Ruff PASS, Format 296, Pyright 0, Default 456 passed/55 deselected,
  격리 Integration 44 passed/5 external-GPU skipped/462 deselected
- Migration: Empty→0010, 0009→0010, 0010→0009→0010과 drift 0, 임시 DB 0. 최초
  round-trip 명령의 잘못된 설명형 revision은 Alembic이 거부했고 실제 `20260827_0009`로 수정
- Runtime: Core 6 healthy, application queue 5개 consumer 1/depth 0, live rules12/replay200/
  duplicate NOOP/tenant404/Vision NOT_EVALUATED
- Git: `git diff --check` PASS. 지정 메시지 `feat: add versioned policy engine core`로 승인
  범위만 로컬 Commit 예정이며 Push·PR 없음; Kaputt 사용자 파일 제외
- 다음 작업: Commit SHA를 확인하고 `feature/sprint-5b-human-review-workflow`에서 immutable
  Review Packet, CAS Task, append-only Action 및 human-only Decision을 구현

### 2026-08-27 — Sprint 5B Human Review Workflow

- Git: Sprint 5A를 `67eafdd feat: add versioned policy engine core`로 로컬 Commit하고
  `feature/sprint-5b-human-review-workflow` 생성. Sprint 5B Commit·Push·PR 없음
- Boundary: Policy success가 identifier-only `human_review.requested.v1`을 원자 저장하고 thin
  Worker는 Task/Packet/CREATED만 생성. Final Decision은 authenticated Admin/Reviewer Resolve만 생성
- Workflow: versioned mapping, immutable packet, five-state machine, CAS claim, release/evidence/
  resume/escalate, assignment history, append-only actions와 decision/basis를 구현
- Authorization: Viewer read-only, Reviewer는 Standard/Evidence/Exception과 자신의 task만 action,
  Manager/Safety/Escalated claim 및 Manager/Safety resolve는 Admin only; cross-tenant는 404
- Integrity: Rule/Citation/Evidence/Analysis basis를 packet/run/tenant allowlist로 검증하고 rationale
  10–2000자를 요구. Decision/Packet은 수정·삭제 경로 없이 content hash와 unique constraint로 보호
- Evaluation: `human_review_workflow_v1` 90건, Dev60 freeze 뒤 sealed Test30 단 1회. mapping,
  priority, transition, authorization, assignment, basis, outcome, audit, replay 모두 1.0; 위반 0
- Verification: Ruff PASS, Format 315, Pyright 0, Default 484/57 deselected, Integration
  46/5 skipped/490 deselected, migration 세 경로 drift 0, 임시 DB 0
- Runtime: 최신 Docker 6 healthy, six application queues consumer 1/depth 0. Live task/packet/
  created/claim/resolve/decision/basis 각 1, duplicate event NOOP, claim/resolve 409, tenant 404
- Failure record: 첫 직접 probe에서 ORM relationship이 없는 aggregate insert flush 순서로 FK 오류가
  발생해 root와 decision을 먼저 flush하도록 수정. 첫 전체 회귀의 8 failures는 이전 migration
  테스트가 0010 head를 고정한 기대값이 원인이었고 0011 단일 head로 갱신 후 전체 통과
- Scope: 실제 환불·교환·결제·CRM·알림·보고서·UI·Decision revision/자동 assignment/SLA 없음.
  Grounding은 advisory, Local LLM은 LOCAL_POC, Vision은 MOCK_QUALIFIED
- Handoff: `docs/progress/SPRINT_5B_HUMAN_REVIEW_WORKFLOW.md`와 ADR-0077~0088이 canonical 인계점.
  `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage이며 다음은 Sprint 5C 설계 검토

### 2026-08-27 — Sprint 5B Async Reliability Closeout

- 판정: P0 0, P1 0, `CLOSEOUT_PASS_WITH_PRODUCT_LIMITATIONS`
- Reliability: Policy Retrieval·Grounding·Policy Evaluation·Human Review Outbox에 claim token,
  lease, publish backoff, `CONSUMED/FAILED`와 실패 기록을 추가하고 fenced dispatcher로 통합
- Worker: Retrieval·Grounding·Policy worker 실행 lease, late-result fencing, bounded retry와 poison
  event의 durable failure를 구현; Human Review는 event 검증부터 Task·Packet·CREATED·CONSUMED까지
  단일 트랜잭션으로 처리
- Integrity: Packet/Decision hash를 조회와 Resolve 직전에 다시 검증하고 basis tenant/run/type/FK
  일치를 fail-closed로 보강; duplicate Resolve도 기존 Decision hash를 먼저 검증
- Verification: Ruff 0, Format 324, Pyright 0, Default 516 passed/59 deselected, disposable
  Integration 48 passed/5 external-GPU skipped/522 deselected, focused reliability 검증 통과
- Migration: Empty→0012, 0011→0012, 0012→0011→0012, drift 0, 임시 DB 잔존 0. 중간 개발형
  0012가 stamp된 live DB도 tolerant downgrade 뒤 최종 round-trip과 drift 0 확인
- Runtime: Core 6 healthy, six application queues consumer 1/depth 0. RabbitMQ 중단 중 event가
  backoff된 뒤 재기동 후 `CONSUMED`; duplicate worker 실행 두 번 모두 `NOOP`, Result 수 불변
- Failure record: 공유 DB Integration에서 dispatcher 경합이 드러나 disposable clone runner로
  격리했다. 중간 0012 live schema의 누락 constraint로 첫 downgrade가 실패해 명시적
  `DROP CONSTRAINT IF EXISTS` 복구 경로를 추가하고 전체 lifecycle을 재통과했다.
- Git: `feature/sprint-5b-human-review-workflow`에서 지정 메시지로 Commit하고 동일 원격 기능
  브랜치에 백업 예정. PR과 `develop` 병합은 거버넌스 PR #2와 보호 규칙 결정 전까지 보류
- Scope: 실제 기업 정책/Case/사용자 분포, 실제 Vision, Qwen3.8 재평가와 운영 UI는 미검증.
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 Commit 제외
- 다음 작업: `feature/sprint-5c-case-resolution-external-action`에서 Resolution Projection,
  immutable Action Intent, 입력 완전성 검증과 네트워크 없는 External Action DRY-RUN 구현

### 2026-08-27 — Sprint 5C Case Resolution, DRY-RUN, and Consultant Console Closeout

- 판정: 내부 시뮬레이션 데모 구현·검증 완료. 현재 제품 판정은
  `SYNTHETIC_MOCK_SIMULATION_DEMO`; Limited PoC는 외부 증거 미확보로 `BLOCKED`
- Git: Sprint 5B를 `4aefae6 feat: add human review workflow`로 Commit·Push했다. Sprint 5C 기능은
  `0a5f529 feat: add case resolution and PoC console`로 Commit하고
  `origin/feature/sprint-5c-case-resolution-external-action`에 백업했으며 PR은 만들지 않았다. 본
  closeout 원장도 동일 기능 브랜치의 후속 문서 Commit에 포함한다.
- Resolution: Case와 별도인 versioned projection/event, exact Decision mapping 1.0.0,
  immutable Action Intent, explicit input only, missing/invalid input과 conflicting Decision
  fail-closed 경로 구현. `cases.status`와 기존 Decision/Packet은 불변
- Reliability: Decision과 Resolution request 원자 저장, Resolution/Simulation별 durable outbox,
  claim/lease/backoff/exact-event validation, execution fencing과 duplicate `NOOP` 구현
- Action: network-free deterministic `DRY_RUN`만 생성하고 모든 Result가
  `side_effects_performed=false`; `LIVE`는 `LIVE_EXTERNAL_ACTION_DISABLED`
- Reporting: terminal Resolution version마다 content-hashed `review_report/1.0.0` snapshot,
  tenant-scoped latest read, tamper rejection, degraded integrity-failure snapshot과 printable UI 구현.
  PoC KPI는 모두 numerator/denominator/sample count와 zero-denominator null을 반환
- Console: React 19·TypeScript·Vite, OpenAPI type/check, memory-only JWT, opaque workflow checkpoint,
  Case/Evidence/analysis/retrieval/citation/policy/review/resolution/report/metrics 화면 구현
- Verification: Backend static PASS, default 554 passed/62 deselected, Integration 51 passed/
  5 external-GPU skipped/560 deselected. Frontend lint/type/OpenAPI/build PASS, Vitest 6,
  Playwright 5. PostgreSQL head `0014`, drift 0
- Runtime: 7 services healthy, 8 queues consumer 1/depth 0. Live Human Decision→Resolution→
  `ACTION_DRY_RUN_VALIDATED`, duplicate `NOOP`, Case status 불변, cross-tenant `404`
- Broker recovery: 실제 RabbitMQ 중단 중 Resolution request가 `PENDING` attempts 3까지 보존되고
  재기동 뒤 `CONSUMED` attempts 5, 최종 Resolution validated
- Demo evidence: Scenario 1은 별도 live backend causal 경로, Scenario 2는 disposable PostgreSQL
  integration을 보유한다. Playwright 5개는 intercepted API fixture이며 특히 Scenario 3–5는
  fixture-driven UI/component-backed로서 live causal E2E라고 주장하지 않는다.
- Remaining promotion evidence: actual `LIVE`, 실제 Data/Policy/Vision qualification, 개인정보
  승인, Shadow Human comparison, 실제 Qwen Extraction/Grounding reevaluation. 하나라도 없으면
  성능·ROI를 실제 PoC 결과로 주장하지 않는다.
- Handoff: 상세 원장은 `docs/progress/SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`, 승격 계약은
  `docs/resolution/SPRINT_5C_DEMO_BOUNDARY.md`. 사용자 소유 루트 문서 두 개는 수정·삭제·Stage하지 않음

### 2026-08-27 — Current Status HTML Dashboard

- 산출물: `docs/progress/CSIGHT_CURRENT_STATUS_2026-08-27.html`
- 목적: Sprint 5B/5C 완료 범위, 검증 수치, 업무 흐름, 5개 데모의 증거 수준, Limited PoC
  미충족 Gate와 다음 실행 순서를 한 화면에서 확인
- 표현 경계: 현재 판정을 `SYNTHETIC_MOCK_SIMULATION_DEMO`로 유지하고 Scenario 3–5를
  fixture-driven으로 표시하며 실제 PoC 성능·ROI를 주장하지 않음
- 구현: 외부 asset이나 네트워크 의존성이 없는 standalone HTML, 반응형 화면과 인쇄/PDF 지원
- 검증: 로컬 exact URL HTTP 200, 핵심 판정·검증 수치·Git 기준점 포함, whitespace diff PASS
- Git 안전: 사용자 소유 루트 문서 두 개는 수정·삭제·Stage하지 않음

### 2026-08-27 — HDP-100 Synthetic Scenario PoC and Binary Vision Contract

- 판정: `SCENARIO_TECH_POC_READY` / offline pack `OFFLINE_SCENARIO_PACK_READY`; 실제 E3 runtime은
  `RUNTIME_VISION_INTEGRATION_BLOCKED`. Limited PoC 판정은 계속 `BLOCKED`
- Scope: 가상 브랜드의 fictional `HDP-100` 수동 펌프형 디스펜서. 실제 기업·고객 Data와 실제
  기업 Policy는 오늘 범위에서 의도적으로 사용하지 않음
- Artifacts: synthetic Case/Gold 36/36, split demo/dev/test 5/21/10, synthetic policy version
  1.0.0의 10 clauses/7 rules, 대표 demo 5개, artifact/pack hash 연결
- Offline verification: required artifact, JSON, synthetic boundary, hashes, Case 수, policy,
  Gold linkage, demo boundaries, binary model manifest의 9 checks 모두 PASS
- E3 evidence: epoch 10 `best.pt` 후보의 AP 0.884863, AUROC 0.931604, threshold 0.8984375는
  담당자 제공 보고서에서 전사한 수치이며 `report_metrics_reproduced_by_csight=false`
- Threshold boundary: score `>= 0.8984375`는 위치·유형 없는 고신뢰 결함 후보다. 더 낮은
  score는 `BELOW_HIGH_CONFIDENCE_THRESHOLD`이며 정상이나 결함 없음 판정이 아니다.
- Runtime: image-level any-defect assessment와 Detection을 분리하고 deterministic Mock binary
  contract만 live 연결. 실제 `best.pt`, checkpoint package, serving endpoint/reference는 부재
- Persistence: additive `20260827_0015_vision_image_assessment`가 현재 DB Head. 실제 E3 metric을
  runtime prediction에 복사하지 않고 score/threshold/outcome만 append-only 저장
- Pending failure record: parallel Text/Vision terminal join race를 수정했으며 live causal
  재검증이 진행 중. 실제 PostgreSQL barrier focused regression은 1 passed/14 deselected지만,
  재검증 완료 전 현재 branch의 새 전체 회귀 수치와 최종 live runtime 판정은
  `PENDING_REVERIFICATION`; 기존 Sprint 5C 554/51 결과는 역사적 기준점으로 보존
- Claim boundary: 실제 E3 추론, HDP-100 제품별 정확도, 실제 고객 성능, 정상 자동 판정,
  실제 기업 정책 검증, 자동 승인, 비용 절감·ROI는 주장하지 않음
- Documentation verification: acceptance/model/manifest/policy JSON 근거 대조 PASS, HTML5 parse
  error·중복 ID 0, 필수 section 10개 확인, 로컬 HTTP 200, whitespace diff PASS. Browser visual
  QA는 연결 가능한 browser runtime이 없어 이번 세션에서 수행하지 못함
- Git safety: `feature/scenario-poc-hard-plastic`, Base `30297c2`, 현재 변경 미Commit.
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 제외

### 2026-08-27 — HDP-100 Scenario PoC Final Regression and Live Recovery

- Root cause: parallel Text/Vision completion transactions at PostgreSQL `READ COMMITTED` each
  observed its own terminal Stage and the peer's uncommitted `RUNNING` Stage, so neither closed the
  parent Run. Tenant/case-scoped parent `FOR UPDATE` locking now serializes claim, completion,
  retry/failure, exhaustion, and Outbox terminal-failure joins.
- Recovery: terminal Stage redelivery now reconciles an orphan `RUNNING` parent without creating a
  second Result. The previously reproduced Run `e5d01e06-5f93-44b5-959e-1c18da81eb71` recovered
  through an actual worker `NOOP` delivery to `SUCCEEDED`, with Result/Assessment/Detection 1/1/0.
- Fresh live path: Run `18451c65-ec11-4beb-a814-a52f695f8505` completed Text and Mock binary Vision
  in parallel as `SUCCEEDED`. It persisted exactly one image assessment, no localized Detection,
  threshold 0.8984375 and deterministic synthetic score 0.965449; normal classification and
  automatic Decision remained false.
- Regression: Ruff PASS, Format 365, Pyright 0; Default 585 passed/65 deselected; disposable
  Integration 54 passed/5 external-vLLM GPU skipped/591 deselected with leftover DB 0.
- Frontend: lint, TypeScript, generated OpenAPI sync and production build PASS; Vitest 9 and
  Playwright intercepted-fixture scenarios 5 PASS.
- Runtime: latest backend/web images rebuilt, PostgreSQL Head `0015`, seven services healthy,
  eight application queues consumer 1/depth 0, five synthetic demo Cases seeded idempotently.
- Verdict: `SCENARIO_TECH_POC_READY` with `MOCK_CONTRACT_ONLY_NOT_E3_INFERENCE`. Actual E3 remains
  `RUNTIME_VISION_INTEGRATION_BLOCKED` until the Vision owner supplies the checkpoint package,
  immutable identity and private serving endpoint.
- Git safety: user-owned root documents remain unmodified and excluded; feature Commit and remote
  branch backup are the next closeout action, with no PR or `develop` merge.

### 2026-08-28 — HDP-100 Final Reverification Closeout

- Backend static: Ruff PASS, Format 365 files, Pyright 0.
- Backend regression: default 603 passed/65 deselected; disposable PostgreSQL Integration 54
  passed/5 external-GPU skipped/609 deselected, leftover DB 0.
- Frontend: lint, typecheck, generated OpenAPI sync and production build PASS; Vitest 10 and
  Playwright intercepted-fixture scenarios 5 PASS. 이 수치는 다섯 시나리오 모두의 live causal
  E2E를 뜻하지 않는다.
- Scenario pack: offline acceptance 9/9, canonical pack hash
  `6be7ad00ba4b92bd99fbcb0ab6c7b9163e387aa8ccd734751c479a2352c24ef1`.
- Live Mock binary path: Run `fc249b72-92b4-4160-adee-2c9b0b66b092` `SUCCEEDED`, score
  0.961864, threshold 0.8984375, localized Detection 0, automatic Decision false.
- Runtime: PostgreSQL Head `0015`, seven services healthy, eight application queues consumer
  1/depth 0, API·Web·상태 HTML HTTP 200.
- External boundary: 실제 E3 endpoint, checkpoint package와 endpoint reference가 없고 runtime
  probe도 실행하지 않아 `RUNTIME_VISION_INTEGRATION_BLOCKED`를 유지한다.
- Git safety: HDP-100 기능 Commit과 원격 기능 브랜치 백업은 아직 `NOT_RUN`이다. 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지
  않았다.

### 2026-08-28 — HDP-100 Feature Commit and Remote Backup

- Commit: `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d feat: add hard-plastic scenario PoC`.
- Branch: local `feature/scenario-poc-hard-plastic`와
  `origin/feature/scenario-poc-hard-plastic`가 동일 SHA임을 확인했다.
- Governance boundary: PR 생성과 `develop` 병합은 실행하지 않았다.
- Documentation boundary: 이 상태 문서 갱신 자체의 Commit SHA는 아직 없으므로 기록하지 않는다.
- Git safety: 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`와
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않았다.

### 2026-08-28 — Real E3 Host Runtime and Synthetic Core Integration

- 목표: 담당자가 전달한 E1–E3 weights/README/SHA를 검증하고 canonical E3만 선택해 오늘의
  HDP-100 합성 기술 PoC에 실제 checkpoint forward를 연결
- Weight integrity: 세 checkpoint의 제공 SHA-256과 재계산값이 모두 일치. E3는 원격
  canonical manifest의 size 264,918,248와 SHA
  `49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e`까지 일치
- Package/runtime: manifest·preprocess·threshold·labels·offline DINOv2 config를 고정하고,
  checkpoint는 Git/Docker 밖의 경로만 허용. unsafe globals 0, `weights_only=True`·mmap,
  exact root/config/tensor count/dtype/finite/strict key를 통과해야만 loopback server가 시작됨
- Direct inference: MPS float32 host runtime health 200. 합성 펌프 connectivity image의 실제 E3
  score 0.5347465873, frozen threshold 0.8984375, 결과
  `BELOW_HIGH_CONFIDENCE_THRESHOLD`, Detection·normal classification·automatic Decision 0
- Core causal path: Docker Worker→host-private endpoint 200. Run
  `893f8927-7c71-4246-936b-5c752493ffc4`가 `SUCCEEDED`로 완료되고 exact model/version/SHA와
  image assessment가 append-only 저장됨
- Failure/recovery: wrong task와 MIME/content mismatch 422, hash drift가 `torch.load` 전 차단,
  symlink 거부. 첫 stop 직후 즉시 health probe는 종료 유예 중 200이어서 재시도 후 closed를
  확인. 첫 setup 재실행은 기존 venv를 거부해 `--allow-existing`으로 수정하고 safe stop→setup→
  restart 뒤 동일 score와 Worker health 200을 재확인. 실제 timeout/malformed-response live
  fault injection은 `NOT_RUN`
- Backend verification: Ruff 0, Format 374, Pyright 0, Default 605 passed/65 deselected,
  disposable Integration 54 passed/5 external-GPU skipped/611 deselected, 임시 DB 0. E3 전용
  package/fail-closed test 5 passed
- Frontend/runtime: lint·typecheck·OpenAPI·build, Vitest 10, intercepted-fixture Playwright 5
  통과. DB Head `0015`, Core 7 services healthy, 8 queues consumer 1/depth 0, API·Web·상태 HTML
  HTTP 200. 브라우저에서 실제 E3 PASS와 product qualification BLOCKED 문구를 직접 확인
- Scope: 실제 checkpoint 연결은 `PASS_WITH_SCOPE`지만 합성 이미지 한 건의 기술 연결일 뿐
  held-out metric 재현, HDP-100 제품 accuracy, 고객 데이터/정책, ROI 증거가 아니다. Kaputt
  권리 범위 때문에 내부 비상업 연구 데모로 제한하고 public/customer/commercial 사용은 차단
- Git: 기존 Scenario 기능·closeout HEAD `5c152fd`는 원격 기능 브랜치와 일치. E3 runtime
  변경은 로컬 미Commit·미Push이며 가중치와 사용자 소유 루트 문서 두 개는 수정·복사·Stage하지 않음
- 다음 작업: HDP-100 5개 대표 합성 이미지·Human Gold·재현 점수를 고정하고 실제
  timeout/recovery와 malformed-response fail-closed를 주입 검증

### 2026-08-28 — Local Demo Admin Identity

- 목표: 상담원 콘솔에서 한 계정으로 일반 검토와 Safety Admin 시나리오를 모두 시연할 수 있도록
  local tenant `csight`와 `csight@csight.demo` 계정 생성
- Persistence: active Tenant 1, active User 1, `ADMIN` Role 1을 한 DB transaction으로 생성;
  비밀번호는 Argon2 hash로만 저장하고 평문은 원장·파일·Git에 기록하지 않음
- Verification: `/api/v1/auth/token` HTTP 200, 발급 Token으로 `/api/v1/auth/me` HTTP 200;
  Principal email과 단일 `ADMIN` Role, tenant user count 1과 account role count 1 확인
- Scope: 현재 loopback local demo 전용. 외부 공개·공유 환경에서는 Credential 교체 또는 계정
  제거가 선행돼야 함
- Git: Runtime DB identity 생성과 상태 원장 갱신만 수행; Commit·Push 없음

### 2026-08-28 — Cloudflare Domain Switch to CSight

- 목표: 개인 지뢰찾기 서버에 사용하던 `doongdoong.org` Cloudflare Tunnel을 현재 CSight 합성
  기술 데모 Web으로 전환
- Routing: root·`www`의 game HTTP `3000`과 `/socket` WebSocket `3001` ingress를 제거하고
  host loopback CSight Web `127.0.0.1:8080`으로 통합; catch-all 404 유지
- Activation: cloudflared ingress validation `OK`, LaunchAgent tunnel process kickstart 성공;
  지뢰찾기 HTTP/WS 서버는 로컬에서 계속 실행되지만 도메인에서는 분리됨
- External verification: root·`www` system-info가 `csight-core-api`, Web health 200; 외부
  `/auth/token`·`/auth/me` 200와 single `ADMIN` Principal 확인, Token cache header no-store/no-cache
- Browser QA: `https://doongdoong.org/login`, title `CSight 상담원 콘솔`, login form DOM과 console
  error 0을 확인하고 사용자에게 보이는 탭으로 인계
- Security boundary: Cloudflare Access 미적용이고 Demo Admin Credential이 짧다. 실제 데이터는
  업로드하지 않으며 외부 공유 전에 Access 또는 Credential 강화가 필요
- Git: Cloudflare local config와 상태 원장만 변경; CSight Commit·Push 없음

### 2026-08-28 — E3 Top-100 Selected-Positive Replay and Core Sample

- 목표: 전달된 E3-correct selected-positive package를 원본 복사 없이 실제 E3와 Core 경로로 재생
- Source integrity: JPEG 100/100의 manifest SHA·decode·2048² RGB·EXIF/ICC 부재를 확인.
  `DEFECT 100 / NORMAL 0`, hard-plastic 14장 모두 major defect이며 package tree SHA는
  `4543f49f9a54a989a694096b89f3be83a47cd1d80c4c46a5e2ab4ff4937cb132`
- Direct E3: exact revision `49e8a64c…1037e`, MPS float32에서 100/100 완료. source threshold
  0.5와 frozen threshold 0.8984375 모두 100/100; score 0.9980715–0.9999757,
  mean 0.9993894, median latency 932 ms
- Core causal sample: 시각 검토 allowlist ranks 003·032·054·058·078·080의
  Case→Evidence→Analysis 6/6 `SUCCEEDED`; Evidence SHA와 direct/Core score delta 0
- Safety audit: 각 Case의 Human Review Task·Resolution Event·Action Intent 0, Resolution GET 404.
  평가기가 Human Decision·Resolution·External Action을 요청하지 않았고 위치 Detection도 0
- Verdict: `TOP100_SELECTED_SUCCESS_REPLAY_AND_CORE_SAMPLE_PASS`; canonical report SHA
  `9400509e18689d6696e303a7f30a803cd1252872d21ff123c28b0b50e1d9d2bf`
- Verification: Ruff 0, Format 376, Pyright 0, 새 focus 9 passed, E3 runtime 5 passed,
  default 612 passed/65 deselected. HTML 구조·local status·external login HTTP와 1324px Browser
  카드/overflow/console 검증 통과; 시각 QA에서 발견한 기존 console-link 세로 배치를 수정. App/API/
  Migration 변경이 없어 disposable Integration 전체 suite는 재실행하지 않고 실제 Core 6건으로 검증
- Claim boundary: positive-only·correct-only 선택 편향 때문에 AP·AUROC·accuracy·recall·정상
  확인·제품 qualification·Limited PoC 승격 근거가 아님. package에 license·annotation provenance·
  공개 재배포 권리가 없고 rank 061에는 개인 이름이 보여 제외; 원본·report는 Git과 공개 Web 밖에 유지
- Git: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`와
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: HDP-100 다섯 대표 이미지·Human Gold 고정, timeout/malformed-response live Gate,
  공개 접속 보호와 데이터 권리 확인

### 2026-08-28 — Realistic 6:4 Internal Demo and Human Review Staging

- 목표: selected-correct 결함만 보이던 기술 재생을 실제 상담 화면에 가까운 10건 구성으로 바꾸고,
  사용자 제공 정상 참고 이미지를 과장 없이 섞어 실제 E3·private Evidence·합성 정책 검토 경로를 확인
- Normal source: JPEG 77장, 2048×2048 RGB, EXIF/ICC·exact duplicate·Top-100 overlap 0. 실제
  E3 77/77이 source 0.5와 frozen 0.8984375 모두 미만이며 score 범위
  0.0000208903–0.0001434958. label 근거는 사용자 진술뿐이고 license·provenance·독립 Gold는 없음
- Frozen 6:4 selection: selected-correct defect ranks 003·032·054·058·078·080과 normal-reference
  ranks 002·008·017·023을 10개 합성 자연어 문의에 연결. 결과는 고신뢰 defect candidate 6,
  threshold 미만 참고 4이며 실제 prevalence·accuracy·normal confirmation이 아님
- Private Evidence: 원본을 Git·Web static에 복사하지 않고 tenant/Case-scoped Evidence API에 저장.
  인증된 same-origin content endpoint가 size/SHA를 fail-closed 재검증했고 최종 replay에서 10/10 일치
- Policy runtime: fictional `csight` corpus 12 Document/84 Clause/84 Qwen3 embedding/ACTIVE index 1,
  Rule/Source link 12/12. local/test와 loopback PostgreSQL/Embedding만 허용하며 existing semantic,
  embedding SHA/vector, exact index metadata가 다르면 자동 수정 없이 실패. 실제 prepare 2회 모두
  bundle/ingestion reuse, embedding created 0
- Live representative flow: `REAL-DEMO-DEFECT-03`과 `REAL-DEMO-NORMAL-01`이 각각 Text v2,
  RAW Top-3 Retrieval, Grounding, Policy Evaluation `SUCCEEDED`와 matching Human Review `PENDING`까지
  완료. E3는 `NOT_LINKED_TO_POLICY_INPUT`; Human Decision·Resolution·Action Intent·Simulation 0
- Idempotency/safety replay: 정책·Review 2건을 만든 뒤 10건 seed를 다시 실행해 Case/Analysis replay
  10, Evidence reuse·authenticated integrity 10, 새 workflow row 0을 확인. workflow before/after는
  Retrieval/Grounding/Policy/Review 각각 2로 동일, canonical report hash
  `8f26ed1ff7f8dca6daf55eee08106651e31ad2fa5cc3ed078cd8070b111cc6b7`
- UI: Bearer-authenticated image Blob preview, source provenance/selection bias/rights badge, E3 score·
  threshold 안전 해석, citation title/body/version, independent run IDs와 Review Packet 원장을 표시.
  최신 FAILED는 이전 성공 결과를 가리지 않고 실패한 Text/Vision branch만 새 key로 재시도
- Verification: Ruff PASS, Format 382, Pyright 0; default 648 passed/65 deselected/36 warnings,
  disposable Integration 54 passed/5 external-GPU skipped/654 deselected and removed; focused E3/demo
  29, E3 runtime 5; Web lint·typecheck·OpenAPI·build, Vitest 32, Playwright fixture 5 PASS
- Runtime/browser: DB Head `0015`, Core 7 services healthy, Qwen embedding 8091과 E3 8093 health PASS,
  Evidence content OpenAPI path 존재·unauthenticated 401. `https://doongdoong.org/login` 새 Web build와
  Login DOM, browser console error 0 확인; rebuild로 기존 browser memory token이 만료되어 로그인 후
  실제 Case 화면 검증은 사용자 세션에서 이어감
- Git safety: Commit·Push·PR 없음. checkpoint·raw image·local reports와 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`는 Git 제외
- 다음 작업: 상담원 콘솔에서 대표 2건을 사람이 직접 검토한다. 승인된 Human Decision이 생기기
  전에는 Review Report·Resolution·DRY-RUN을 생성하지 않고, 공개 공유 전 Access/credential과
  데이터 권리 경계를 먼저 보강한다.

### 2026-08-28 — R1 Visual-Aligned Inquiry, Three-Column Console, and Policy 2.0.1

- 목표: 짧고 이미지와 어긋날 수 있던 상담 문구를 실제 이커머스 반품·교환·환불 문의처럼 확장하고,
  상담원이 고객 주장·이미지·가상 사내 정책을 한 화면에서 비교할 수 있는 내부 데모를 완성
- R1 inquiry contract: 결함 후보 6·기준 미만 참고 4의 10건을 각 4~5문장으로 고정하고
  `demo_image_observation`과 `CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS`를 분리. 실기업명·
  이메일·전화번호는 manifest validation에서 차단하고 legacy v2 Case는 삭제 없이 UI에서 숨김
- Seed/replay: R1 10 Case/Evidence/실제 E3를 생성한 뒤 같은 입력을 재실행해 Case/Analysis 10 replay,
  Evidence reuse·integrity 10, 신규 workflow row 0을 확인. canonical report hash는
  `6a7b9af27016ea9a88141878cdbadaca71b2e3ea660f9b47c9d944c4f7002dba`
- UI: Case 상세의 최상단을 `문의 내용 / 이미지 근거 / 정책 기반 권고` 3열로 정리하고 가상 문의·
  가상 사내 정책 배지, 사진 관찰/고객 진술 경계, exact E3 binary identity를 표시. 실행 ID·Workflow·
  Resolution은 하단 접이식 보조 영역으로 이동하고 bbox가 섞인 binary 결과는 fail-closed 처리
- Fictional policy: CSight Commerce 운영규정 8 Document·52 Clause와 25 typed Rule·35 Source를
  추가. 기존 포함 전체 20 Document·136 Clause이며 문서·retrieval index는 `2.0.0`, canonical
  Rule Set/Rules는 `2.0.1`로 고정
- Reliability recovery: 최초 v2 `2.0.0`에서 다중 source 순서와 DB 재구성 순서가 달라 immutable
  hash mismatch가 발생한 원인을 확정. production reconstruction과 ingest에 canonical 정렬을 강제하고,
  faulty `2.0.0`·failed Evaluation/Outbox는 삭제 없이 frozen hash가 일치하는 RETIRED 이력으로 보존.
  clean 환경은 v1+2.0.1만 만들며 live DB는 v1/2.0.0 RETIRED, 2.0.1 sole active
- Policy replay: prepare 1회에서 successor Rule 25를 추가하고, 2회째 bundle/ingestion exact reuse와
  insert 0을 확인. 현재 감사 이력 포함 Rule/Source는 62/82, active Rule Set은 1개
- Live representative flow: R1 rank 054 수리, rank 078 Safety, rank 008 단순변심 3건이 각각
  Text v2→RAW Top-3→Grounding→Policy `2.0.1`을 `SUCCEEDED`했고 matching Human Review 3건이
  `PENDING`. Top-3는 모두 `CSC-OPS-* / 2.0.0`; R1 10건의 Decision·Resolution·Intent·Attempt·Result 0
- Verification: Ruff PASS, Format 384, Pyright 0; default 658 passed/65 deselected/36 warnings;
  disposable Integration 54 passed/5 external-GPU skipped/664 deselected/5 warnings and removed;
  policy focus 19; Web lint·typecheck·OpenAPI sync·build, Vitest 39, Playwright fixture 5 PASS
- Runtime/browser at 12:48 KST: Docker 재시작 후 E3·Qwen Embedding MPS와 Core 7 services healthy,
  DB Head `0015`, API live/ready·Web health PASS, Core는 exact E3 remote identity 사용. 공개 Login은
  title/DOM/가로 overflow/console warning·error 0을 확인했고 비밀번호 입력이나 Human Resolve는 하지 않음
- Scope: 10건·정책은 모두 가상이며 E3 score는 policy input과 미연결. selected-correct 6:4와 권리
  미확인 이미지는 제품 성능·실제 분포·상업 PoC 근거가 아니며, Access·강한 Credential·재배포 권리
  확보 전 `doongdoong.org` URL과 계정을 제3자에게 공유하지 않음
- P2: policy input snapshot의 Vision qualification이 미연결 상태에서도 `MOCK_QUALIFIED`이고,
  `case.order_amount`가 generic attributes provenance를 사용한다. 현재 R1 seed에는 금액 입력이 없고
  최종 조치를 만들지 않지만 실제 데이터 전 source-tagged typed schema 보강이 필요
- Git safety: Commit·Push·PR 없음. checkpoint·raw image·local reports와 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 대표 Review 3건은 인증된 사람이 실제 판단할 때만 Resolve한다. 외부 공유 전
  Access/Credential과 권리 경계를 보강하고, 제품 적용 전에는 권리 확인된 자체 표본·Human Gold와
  policy input provenance를 별도 qualification한다.

### 2026-08-28 — Consultant-first Workspace UX and Policy Date Recovery

- 목표: 실사용 상담원이 첫 화면에서 다음 행동을 바로 이해하도록 Case Workspace를
  단순화하고, 우측 `이어하기`가 정책 평가에서 반환하던 HTTP 422를 해소
- UX: 상단에 `지금 할 일` 단일 주요 CTA와 문의 접수→사진 확인→정책 검토→
  담당자 결정 4단계를 추가. 본문은 문의·이미지 맥락과 정책 권고의 2열로 재배치하고,
  모델 identity·실행 ID·Resolution은 접은 상세로 유지. 상시 노출되던 기능 없는
  데스크톱 X는 제거하고 모바일 사이드바가 열렸을 때만 닫기 버튼을 표시
- 422 원인: Case `created_at` UTC `2026-08-27`을 문자열로 잘라 정책 기준일로 사용했지만,
  한국 업무일은 `2026-08-28`이었고 active Rule Set `2.0.1`도 그날부터 효력이었음.
  API log와 DB rule 효력일을 조회해 `No active policy rule set is valid for as_of_date` 경로를 확정
- 수정: Web이 Case 시각을 `Asia/Seoul` 업무일로 변환한 후 정책 평가를 요청하고,
  서버의 `{error: {code, message}}` 계약을 클라이언트가 정상 파싱하여 재발 시에도
  포괄적 422 문구 대신 실제 이유를 표시
- 검증: OpenAPI generated snapshot sync, ESLint, TypeScript, production build PASS; Vitest
  14 files/42 tests, Playwright fixture scenario 5 PASS. 13:22 KST Core 7 services healthy,
  API readiness·Web health·외부 tunnel health PASS
- 미실행: rebuild로 브라우저 memory token이 초기화되어 인증된 실제 Case에서
  CTA 수동 클릭은 재로그인 후로 인계. 자동 회귀와 비인증 live health는 통과
- 보안·업무 경계: Policy·Vision은 권고만 제공하고 인증된 사람만 최종 결정.
  이번 세션에서 Decision·Resolution·Action을 생성하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 재로그인한 뒤 기존 422 Case에서 `분석 계속하기`를
  한 번 누르고 Policy `2.0.1` 성공 또는 기존 성공 실행 복구를 확인

### 2026-08-28 — Human-confirmed Quick Review and Automatic Report Flow

- 목표: 담당자가 복잡한 Decision form을 작성하지 않고 `허용/비허용`만 눌러도 검토 확정부터
  Resolution·DRY-RUN·최종 검토 문서까지 이어지는 PoC 기술 흐름 구현
- Decision boundary: 모델·정책·Worker가 Decision을 만들지 않으며 인증된 담당자의 명시적 클릭만
  기존 Human Resolve를 호출. Safety·Manager·Policy Exception은 Reviewer를 차단하고 Admin만 허용
- Readiness Gate: threshold `0.70`. Human Review 상태 0.35 + immutable Rule 0.25 + Citation 0.15 +
  qualification metadata 0.10 + 단일 policy eligibility mapping 0.15. 모델 accuracy나 Vision
  threshold가 아니라 PoC 화면 단순화를 위한 workflow-readiness이며 ADR-0097에 고정
- Allow mapping: `RETURN/REFUND_REVIEW`→`APPROVE_REFUND`, `EXCHANGE_REVIEW`→
  `APPROVE_EXCHANGE`, `RESHIPMENT_REVIEW`→`APPROVE_RESHIPMENT`, `REPAIR_REVIEW`→
  `APPROVE_REPAIR`. 복수·미지원 mapping은 허용을 비활성화하고 상세 검토로 fail-closed
- Deny mapping: Gate를 통과한 담당자의 `비허용`은 `REJECT_REQUEST`. 첫 Rule+Citations를 immutable
  basis로 자동 첨부하고 고정된 투명 rationale을 기록하며 고객 원문·LLM·Vision score로 Action을 추론하지 않음
- Client flow: PENDING/허용 권한 상태에서 한 번의 클릭으로 CAS Claim 후 갱신 version으로 Resolve.
  기존 비동기 Resolution/Simulation worker와 `review_report/1.0.0`을 polling하고 생성 즉시 인쇄 가능한
  보고서 화면을 자동으로 열며 별도 server Workflow Coordinator나 mutation API는 추가하지 않음
- UX: 우측 Decision Panel의 주 동작을 큰 `허용/비허용` 두 버튼과 준비도 meter로 단순화.
  상세 Decision·자료 요청·이관·반환은 접힌 예외 경로로 유지하고 버튼 클릭 시 immutable 최종 결정임을 명시
- Verification: OpenAPI sync, ESLint, TypeScript, production build PASS; Vitest 15 files/45 tests,
  Playwright fixture 5 PASS. 첫 시나리오는 Claim expected v1→Resolve v2, `APPROVE_REPAIR`,
  Rule+Citation, Report 자동 navigation과 side effects 0을 검증
- Runtime/browser: 13:50 KST Web rebuild, Core 7 services healthy, API ready·Web·외부 tunnel
  health PASS. 공개 Login title/DOM과 console warning/error 0; 비밀번호 입력이나 실제 Human Resolve는 미실행
- Scope: `0.70`을 성능·정확도·위험 확률·Limited PoC 증거로 주장하지 않음. 실제 상담원 clickstream과
  Shadow Gold 전에는 합성 데모용이며 LIVE 외부 실행과 Case Closure는 계속 없음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 인증 담당자가 비Safety 대표 Case 하나의 정책/근거를 확인한 뒤 실제 `허용` 또는
  `비허용`을 선택하고 생성된 immutable Decision·Resolution·Report를 확인

### 2026-08-28 — Reference-informed Refund Processing Confirmation

- 목표: Human Decision 이후 생성되는 환불 보고서를 실제 이커머스 운영자가 읽는 환불 처리 문서와
  유사한 구조로 개선하되, 특정 기업 서식 복제와 실제 환불 완료 오인을 방지
- Reference: Shopify 공식 환불 안내의 금액·수량·배송비·사유·환불수단·고객 통지·timeline,
  Stripe 공식 환불 안내의 원결제수단·pending/succeeded/failed lifecycle, 국내 전자상거래법
  제18조의 환급·결제업자 취소 요청 관점을 공통 필드로 채택. 상세 근거와 경계는
  `docs/resolution/REFUND_PROCESSING_CONFIRMATION.md`에 기록
- 구현: `APPROVE_REFUND` 또는 `REFUND` Intent를 감지해 `환불 처리 확인서`로 렌더링. 문서번호,
  주문/SKU, 금액·통화·수량, 승인 근거, 취소 요청·통지·RMA/추적, 처리 이력, 정책/담당자 승인,
  Report/Packet/Decision/Intent/Result 감사 ID·Hash를 화면과 A4 인쇄에 구성
- Fail-closed: snapshot에 없는 값은 추정하지 않으며 금액·통화 누락은 `입력 필요`와
  `환불 정보 보완 필요`로 표시. 외부 결제/회수/통지 식별자는 `미요청/미발송/미연동`,
  `side_effects_performed=false`는 `실제 환불 미실행`으로 고정
- Verification: TypeScript·ESLint·production build PASS; Vitest 17 files/49 tests,
  Playwright 다섯 fixture scenario PASS. 1440px full-page 캡처로 데스크톱 문서 밀도·표·timeline·
  감사 footer를 직접 확인. 신규 환불 문서는 backend 계약 변경 없이 immutable report snapshot만 사용
- Runtime/data: Web/API 이미지를 재빌드해 현재 데모에 반영. 14:04 KST DB Head `0015`, Core 7
  services healthy, API ready와 local/public Login HTTP 200. 실제 인증 Human Decision과 외부 환불은 실행하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`와 새 미추적 개인 자료를 수정·삭제·Stage하지 않음
- 다음 작업: 인증 담당자가 명시적으로 환불을 허용한 complete refund Case에서 18,900 KRW 같은
  제출 입력이 문서에 표시되고 DRY-RUN 결과/실제 부작용 없음이 고정되는지 live UI로 확인

### 2026-08-28 — GitHub PoC, MVP, and Release Branch Audit

- 목표: `CSightICT/csight-core`에 PoC·MVP·최종 단계용 branch가 실제로 존재하는지 확인하고
  현재 로컬 구현과 원격 저장 상태의 차이를 확정
- 원격: private repository, default `main`, 총 7 branches. 명시적 `poc`, `mvp`, `final`,
  `release/*` branch와 tag는 없음. 경량 GitFlow 문서상 장기 branch는 `main/develop`만 유지
- Stage mapping: 현재 PoC 작업선은 `feature/scenario-poc-hard-plastic@5c152fd`, 다음 MVP 통합
  후보는 `develop@4037d73`, 최종 릴리스 기준은 `main@4037d73`. PoC는 main/develop보다
  21 commits ahead, Sprint 5C branch보다 2 commits ahead이고 뒤처짐 0
- CI/PR: PoC head push CI success. Governance PR #2는 open, Vision PR #4는 Draft/open이며
  `feature/3-kaputt-dinov2-training@3e2d596` latest push/PR CI success. PoC branch PR은 없음
- Divergence: Vision branch와 PoC branch는 `4037d73`에서 갈라져 Vision-only 55 commits,
  PoC-only 21 commits. 자동 fast-forward나 무검토 직접 merge 대상이 아님
- Local gap: local HEAD는 remote PoC와 같지만 후속 구현이 tracked 44 files, untracked 36 paths로
  남아 있음. E3 runtime, replay/demo/policy, 상담원 UX, 422/quick review/refund document가 원격 미반영
- 판정: GitHub 최신화 필요. 그러나 `main/develop` 직접 Push나 영구 `mvp/final` branch 생성이
  아니라 변경을 논리 단위로 분리 검증한 PoC backup→PR to `develop`→release/tag→`main` 순서가 맞음
- 실행: GitHub/로컬 read-only 감사와 이 원장 갱신만 수행. Commit·Push·branch 생성·PR 수정·병합 없음
- 다음 작업: 사용자 소유 자료를 제외한 Commit 후보 목록을 먼저 확정하고, 전체 회귀 뒤 사용자의
  명시적 승인으로 PoC branch backup을 갱신한다. 이후 Vision PR #4 통합 순서를 별도 결정

### 2026-08-28 — Realistic PoC Safe Commit Preparation

- 목표: 원격보다 앞선 E3 runtime·현실형 데모·가상 정책·상담원 UI를 사용자 소유 자료와 분리해
  검토 가능한 PoC Commit으로 고정하고 fast-forward 원격 백업 전 안전 Gate를 재확인
- Commit: E3/backend/policy/scenario `0f4de4b feat: add E3-backed realistic demo runtime`,
  상담원 UI/빠른 검토/환불 문서 `b3e09cf feat(web): streamline consultant review and refund reports`.
  이 원장을 포함한 상태 문서 Commit과 원격 Push는 아직 미실행
- 전체 검증: Ruff PASS, Format 384, Pyright 0; 기본 658 PASS/65 deselected,
  disposable Integration 54 PASS/외부 GPU 5 Skip/664 deselected 후 DB 정리, Vision E3 5 PASS.
  Web lint·typecheck·OpenAPI sync·production build, Vitest 17 files/49 tests, Playwright 5 PASS
- Data/runtime 검증: 합성 Scenario acceptance 9/9, 정책 DB 24 Document/168 Clause와 mismatch 0,
  Rule Set 2/Rule 24/forbidden decision effect 0. DB Head `0015`, Alembic drift 없음,
  Core 7 services healthy, API ready·local Web·public Login HTTP 200
- 승격 판정: `make verify-poc-readiness`는 정상 종료했지만 외부 증거 Gate가 비어 있어
  `SYNTHETIC_MOCK_SIMULATION_DEMO`를 유지. 실제 기업 데이터·정책·ROI·제품 Vision qualification을
  확보했다는 주장으로 승격하지 않음
- Git safety: 후보에서 Secret·5 MiB 초과 파일·가중치·checkpoint·원본 이미지 0. 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`,
  `ecommerce_vibe_coding_cs_automation_market_research.md`는 수정·삭제·Stage하지 않고 미추적 보존
- 미실행: 인증 Human Decision 클릭, 실제 외부 환불, PR 생성, `develop/main` 병합, 원격 Push·CI
- 다음 작업: 상태 문서 Commit 뒤 원격 PoC가 기존 `5c152fd`인지 다시 확인하고 fast-forward Push,
  GitHub Actions 성공을 관측한 후 정확한 원격 SHA와 Run을 이 원장에 추가

### 2026-08-28 — Realistic PoC Remote Backup and CI Closeout

- 목표: 검증·분리한 세 Commit을 현재 PoC 작업선에만 안전하게 백업하고 원격 회귀 결과를 확정
- 원격 경합 확인: Push 직전 `origin/feature/scenario-poc-hard-plastic`가 감사 기준 `5c152fd`와
  동일하고 local이 정확히 3 commits ahead임을 fetch로 재확인
- 범위 감사: 115 changed files, 금지된 image/checkpoint/archive 확장자 0, 5 MiB 초과 blob 0,
  고신뢰 Secret pattern 0. 사용자 소유 미추적 문서 3개는 staging과 Commit 범위 밖에 유지
- Push: `5c152fd..81b6e20` fast-forward. `develop`, `main`, Vision branch, PR, tag, release는 변경하지 않음
- GitHub CI: Run #108, head `81b6e207e1a593c2f3f3f44cc2fde441a49498c1`, conclusion `success`.
  `Quality and fast tests`와 `Consultant console` 두 Job 모두 PASS
- 판정: 최신 현실형 내부 기술 데모 변경은 원격 PoC에 백업 완료. 합성 정책·선별 이미지·제품
  qualification 미완료 경계와 Human-only final decision은 그대로 유지
- 다음 작업: 이 closeout 원장 Commit의 최종 CI를 확인한 뒤, Vision Draft PR #4와의 충돌 검토 및
  거버넌스 승인 전에는 PoC PR·`develop/main` 통합을 실행하지 않음

### 2026-08-28 — Fictional Product and Price Scenario Catalog

- 목표: 현재 R1 사진 10건이 기술용 `product_ref` 대신 실제 이커머스 상담처럼 읽히도록
  가상 상품명·SKU·가격대·문의 목적을 연결하되 실제 상품/가격 추론과 Action 입력을 분리
- 비용 절감: 저비용·낮은 추론 서브에이전트는 기존 manifest 감사와 초안만 수행. 최종 매핑은
  현재 10장 contact sheet와 source rank를 직접 대조하고 코드/안전 검증은 주 작업에서 수행
- 구현: `web/src/demo/productScenarioCatalog.ts`에 6 defect candidate·4 below-threshold reference
  카탈로그를 고정. 목록은 상품명 검색과 상품명·가상 SKU·가격대를 표시하고 상세는 가상 상품 배지,
  상품군·문의 목적·`실제 판매가/환불 금액 아님` 경계를 표시
- 안전 경계: 가격 basis는 `SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH`. representative price를
  External Action 입력으로 사용하지 않으며 미매칭 Case는 기존 `product_ref`만 표시. 기준 미만 사진을
  정상으로 확정하거나 실제 SKU·브랜드·판매가를 식별하지 않음
- 문서: 현실형 v2 README에 10건 상품/가격 표와 표시·검색·비추론 계약을 추가
- 검증: Web lint·typecheck·OpenAPI sync·production build PASS, Vitest 18 files/52 tests,
  Playwright 5 PASS, `git diff --check` PASS. Web 재빌드 후 Core 7 healthy, API ready·Web health·
  public Login HTTP 200, 새 Login DOM과 console warning/error 0
- 미실행: 브라우저에 Credential을 다시 입력하지 않아 인증 Case 상세 수동 확인과 Human Decision은
  미실행. 추가 사진 후보를 active catalog에 넣거나 원본 이미지를 Git/Web static으로 복사하지 않음
- Git: 변경은 로컬 미Commit·미Push. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 로그인한 Case 상세에서 상품 카드가 사진/문의와 함께 보이는지 확인하고,
  추가 사진은 PII/브랜드/바코드·권리·SHA·E3 outcome 검토 후 별도 catalog version으로 확장

### 2026-08-28 — Synthetic Commerce Context and Refund Document R2

- 목표: PoC Case와 환불 확인서를 실제 이커머스 운영처럼 읽히게 하되 합성 고객/거래 문맥과
  External Action 입력을 분리
- 계약: `synthetic_commerce_context/1.0.0`을 Case JSONB 예약 속성으로 추가. 고객 ID·이름·멤버십,
  마스킹 전화/결제수단/운송장, 상품·판매자·결제 합계, `데모/가상` 배송지만 허용하고 금액 합계와
  timezone을 검증. ADR-0098에 display-only/비추론 경계를 고정
- 구현: Case 목록에 고객명·ID·결제금액, 상세에 고객/주문/배송 카드, 새 terminal Report에 검증된
  Commerce allowlist snapshot과 `direct_contact_values_included=false`를 저장. 환불 확인서는 원 결제액,
  명시 환불액, 마스킹 결제수단, 고객/수령인/배송지를 분리 표시
- DB/E3: 첫 `COMMERCE_CONTEXT_R2` 시도는 Core가 Mock 설정이라 첫 Case의 provider identity에서 즉시
  중단했고 Decision/Action 0. 해당 진단 Case는 append-only 보존하되 목록에서 제외. Core를 Remote E3로
  복구한 `COMMERCE_CONTEXT_R2_E3`은 10 Case·10 Evidence·10 actual E3 Analysis를 신규 생성하고 모두
  `SUCCEEDED`; Policy/Review/Decision/Action 신규 행 0. 같은 시드 재실행은 Case·Evidence·Analysis
  10/10을 재사용하고 Private Evidence 무결성을 다시 확인
- 금액 검증: R2 10건 모두 Commerce snapshot 존재. REFUND 2건은 결제금액/명시 환불액이 각각
  18,900/18,900원, 15,900/15,900원. 결제금액에서 Action parameter를 추론하는 경로는 없음
- 회귀: Ruff·Format 386·Pyright 0, 기본 664 PASS/65 deselected, 격리 Human Review→Resolution→Report
  통합 1 PASS와 임시 DB 정리. Web lint·typecheck·OpenAPI sync·build, Vitest 19 files/55 tests,
  Playwright 5 PASS
- Runtime: 15:38 KST Core 7 healthy, API ready·Web health·public Login HTTP 200, API/Worker/Dispatcher
  `VISION_PROVIDER=remote`와 E3 model/task identity 확인
- 미실행: 인증 Human Decision 클릭, 실제 외부 환불/통지/회수, 기존 immutable Report 소급 변경,
  Commit·Push·PR. 기존 사용자 소유 미추적 문서 3개는 보존
- 다음 작업: 로그인한 사용자가 R2 환불 Case `...002` 또는 `...010`에서 정책 흐름을 진행하고 명시적
  허용/비허용을 선택한 뒤, 새 immutable 환불 확인서에 고객·결제·배송 스냅샷이 표시되는지 확인

### 2026-08-28 — Natural Business UI, Customer Communication, and Tenant Data Assets

- 목표: 내부 enum을 상담원이 읽는 자연어로 바꾸고, 최종 처리 뒤 고객 안내 메일이 어떻게 보이는지
  실제 발송 없이 시연하며, 향후 drift 기준선을 위한 고객사 소유 데이터 축적 경로를 추가
- UI: `APPROVE_REFUND`, `ACTION_NEEDS_INPUT` 같은 코드는 `환불 승인`, `처리 정보 보완 필요`를
  주 라벨로 표시. 상세 결정 select·완료 요약·Resolution·환불 확인서에도 같은 업무 용어를 적용
- Communication: terminal `review_report/1.0.0`만 근거로 immutable EMAIL simulation v1.1을 생성.
  환불 검증 완료·입력 보완·검증 실패를 구분한 제목/본문을 만들고 `SIMULATED_NOT_SENT`,
  `side_effects_performed=false`를 DB check와 UI에 고정. 기존 v1.0 기록도 append-only 조회 호환
- Data asset: `case_learning_asset/1.0.0`을 terminal Report 생성 transaction에 자동 적재. 상품/요청,
  사람 결정, Resolution/Simulation 결과, 모델·정책·pipeline 버전만 allowlist하고 고객 원문·직접
  연락처·주소·담당자 rationale는 제외. 기존 Report는 Migration에서 같은 계약으로 소급 적재
- Drift Gate: tenant별 30건 전 `기준 데이터 수집 중`, 30~59건 `비교 데이터 수집 중`, 60건부터
  `드리프트 점검 준비 완료`. 현재 `csight` 6건으로 수치 판단을 보류하고 분포·버전 현황만 표시
- DB/API: additive `20260828_0016_communication_learning_assets`, Communication POST/GET와
  `/api/v1/data-assets/summary` no-store tenant API. 현재 DB Head `0016`, 기존 Report 9건 중 무결성
  정상 9건을 전체 tenant asset으로 backfill했고 `csight` 조회는 6건
- 검증: Ruff·Format 313·Pyright 0, 기본 672 PASS/59 deselected·6 external Skip, disposable
  PostgreSQL Migration 2 PASS/DB 제거. Web TypeScript·ESLint·OpenAPI sync·production build,
  Vitest 21 files/57 tests PASS. 배포 Login DOM·button 확인
- Runtime: 16:02 KST API/Worker/Dispatcher/Web healthy, PostgreSQL/RabbitMQ/MinIO ready. Core의
  Remote E3 model/revision/threshold identity를 rebuild 뒤에도 확인. live mail v1.1 생성·v1.0/v1.1
  재조회, 모든 상태 `SIMULATED_NOT_SENT`, side effects 0
- 미실행: 실제 SMTP, 외부 고객 통지, 환불/결제 취소, 새 Human Decision, Commit·Push·PR.
  사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 새 R2 환불 Case를 사람 판단으로 처리한 뒤 새 환불 확인서와 안내 메일을
  함께 확인하고, 표본 30건 도달 시 allowlist 누락·분포·버전 기준선을 사람 승인으로 고정

### 2026-08-28 — Runtime Memory Ready Baseline

- 목표: 현재 로컬 PoC가 차지하는 메모리를 Docker Core와 host MPS 모델 서비스로 분리해 운영
  기준점으로 고정
- 측정: 16:28 KST, 호스트 32 GiB. Vision E3 physical footprint 1,570 MiB, Embedding endpoint와
  helper 1,732.5 MiB, Docker Core 7개 961.95 MiB, Cloudflare tunnel 48.42 MiB
- 합계: CSight 귀속 약 4,312.87 MiB/4.21 GiB, 호스트의 약 13.16%. Vision·Embedding 두 모델이
  76.6%, Docker Core가 22.3%, tunnel이 1.1%
- Docker 상세: Worker 258.7, MinIO 153.2, PostgreSQL 149.3, API 141.9, RabbitMQ 131.9,
  Dispatcher 117.8, Web 9.152 MiB
- 상태: Core 7개, Vision E3, Embedding healthy. Reranker·Local LLM은 미실행이라 0 MiB.
  memory-pressure 여유 지표 80%, 측정 시 swap-in/out 0
- 경계: idle/ready 단일 시점이며 모델은 MPS physical footprint, Docker는 cgroup, 작은 host
  process는 RSS를 사용했다. 공유 page/cache와 Docker VM accounting 때문에 시스템 전체 resident
  memory와 정확히 일치하지 않음
- 문서: `docs/progress/MEMORY_USAGE_BASELINE.md`에 측정 계약, 모듈별 표, 개별 peak와 다음 부하
  측정 순서를 기록
- 검증: 두 모델 health, Core 7 healthy, 산술 합계·비중 재계산, `git diff --check` PASS
- 미실행: 대표 10 Case 연속 부하, 동시 사용자, queue backlog, Reranker·Local LLM 추가 적재,
  Commit·Push·PR
- 다음 작업: 대표 10 Case 처리 중 5초 간격 current/peak와 queue depth·실패율을 함께 기록해
  p95/peak 운영 기준점을 append-only로 추가

### 2026-08-28 — Kaputt Source Recovery and Qwen3.8 VLM Sample Qualification

- 목표: 4090 Node에 이미 받은 Kaputt 원본을 재사용하고, 기존 text-only Qwen 경계를 보존한 채
  경질 플라스틱 상품 메타데이터의 offline 후보 라벨링·구조화 가능성을 확인
- Source: `/home/data/datasets/kaputt/extracted`에 Query 이미지 100,267장이 Parquet 행과 정확히
  일치. `plastic_hard`는 10,095건이며 defect 1,323·negative 8,772. Reference image/crop/mask는
  parent의 공식 archive에는 있으나 전량 추출되지 않음
- 구현: 별도 `csight-qwen3.8-27b-vlm` compose, strict JSON schema·deterministic balanced sampling·
  source SHA/model+prompt+preprocess provenance·append-only success/failure 기록 Script, ADR-0099와
  data contract 문서 추가. 실패 기록은 보존하되 성공 전에는 재시도할 수 있게 수정
- Runtime: pinned native VLM을 RTX 4090에 별도 private port로 적재. 첫 0.98 reservation은 가용
  VRAM 경계에서 fail-closed하여 0.95로 낮췄고, 이후 healthy. 기존 ADR-0012 text-only endpoint와
  Core provider는 변경하지 않음
- 표본: prompt 1.2.0으로 test의 defect 2·negative 2를 처리해 4/4 schema success, 9.3–10.8초/건,
  generic-only·중복 defect 0·민감 패턴 0. 사람 점검에서 사탕 용기 1건만 유용했고 머핀 트레이·
  바디케어 용기·접착제 용기 3건은 `UNCERTAIN`; defect-positive 두 건도 기준 비교 없이는 보류
- 판정: Pipeline 기술 검증은 PASS, label quality는 `QUALIFIED_WITH_LIMITATIONS`. 전체 10,095건
  Batch를 실행하지 않고 paired Reference 30건 Human spot-check를 다음 Gate로 설정
- 보존/정리: private derived JSONL SHA-256
  `390f7d32a1b9a689d4071c59d2e8c0493851c7ea5ea3659f9af7ab58913b0d57`; 전용 VLM Container를
  exit 0으로 중지해 GPU 22,365 MiB에서 95 MiB로 회수. 최초 탐색 중 받은 중복 sample 1.1 GiB는
  `/home/user/csight-kaputt-vlm/kdd-5305ccf`에 남겼으며 삭제는 사용자 승인 전 미실행
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 4 PASS, compose/runtime health·model identity,
  output schema/민감 패턴/사람 이미지 점검 PASS. 전체 Backend/Web 회귀는 이번 독립 offline 도구
  변경에서 재실행하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 공식 Reference archive에서 위 30건의 대응 image/crop만 선택 추출하고 Query↔Reference
  pair manifest를 만든 뒤 Qwen 결과를 사람 검수해 full-batch 실행 여부를 결정

### 2026-08-28 — Qwen Query+Reference Images and Comparison Prompt Correction

- 정정: 직전 실행도 Query 사진+Prompt를 함께 보냈지만 기준 사진이 없었다. 사용자 지적에 따라
  입력 계약을 Query Crop 1장+동일 `item_identifier` Reference Crop 1장+역할이 명시된 비교 Prompt로
  수정하고 schema를 `kaputt_vlm_enrichment/2.0.0`, prompt를 `2.0.1`로 갱신
- Data: 공식 31.6 GiB Query Crop과 41.6 GiB Reference Crop archive 전체를 풀지 않고 test 표본에
  필요한 각 4장만 선택 추출. Query/Reference 상대경로·SHA·preprocess와 full Query context 경로를
  append-only 결과에 보존
- Runtime: 별도 VLM의 prompt당 image 제한을 1→2로 변경하고 pinned model/revision은 유지. 기존
  Core text-only Qwen·E3·DB·Human Review는 변경하지 않음
- 실행: defect 2·negative 2 paired 표본 4/4 strict schema success, 9.6–12.0초/쌍,
  `QUERY_PLUS_REFERENCE` 4/4, 민감 패턴 0. 결과 SHA-256
  `159f5ded7eb9559d5b322ca9d24d48cfc117ed4c94a922f89c7145cb8bac3811`
- 품질 판정: 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2로 FAIL. 사진+Prompt 전달 경로는
  동작하지만 Qwen3.8 generic VLM을 Kaputt defect labeler나 E3 대체로 사용하지 않음. 공식 Label은
  Ground Truth, E3는 결함 Vision, Qwen은 선택적 상품 설명 후보로 분리
- 자원: private derived JSONL을 보존하고 전용 Container exit 0, GPU 95 MiB로 회수
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 5 PASS, Compose config PASS, live paired
  4건·schema/provenance/민감 패턴·사람 이미지 대조. 전체 Backend/Web 회귀는 미실행
- Git safety: Commit·Push·PR 없음. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 상품 메타데이터가 필요하면 사람이 일반 상품 유형을 붙인 paired 30건에서 Qwen 보조
  유용성을 따로 평가하고, 결함 Target은 공식 Label/E3에 고정

### 2026-08-28 — Qwen3.8 Paired VLM Runtime Restart

- 사용자 지시로 전용 `csight-kaputt-vlm-qwen38-vlm-1` Container를 다시 시작
- 18:42 KST health `healthy`, 인증 `/v1/models` HTTP 200, served identity
  `csight-qwen3.8-27b-vlm` 확인
- RTX 4090 24,564 MiB 중 21,511 MiB 사용, idle utilization 0%, 39°C
- Query Crop+Reference Crop+Prompt용 image 2개 계약과 private Tailscale bind `:18001` 유지
- 실제 추가 Batch·DB/API 변경·Commit·Push·PR은 실행하지 않음. 품질 Gate FAIL과 공식 Label/E3
  경계는 그대로 유지
- 다음 작업: 승인된 소량 paired metadata 작업만 실행하고, full 10,095건 Batch는 별도 품질 승인 전 금지

### 2026-08-28 — Kaputt Paired 30 Qualification and Product Metadata Split

- 범위: 사용자 `진행해` 지시에 따라 full 10,095건 대신 deterministic paired 30건을 defect 15·
  negative 15로 고정. 기존 4쌍 재사용 후 Query Crop 26장·Reference Crop 24장만 공식 archive에서
  선택 추출해 Query 30/30·unique Reference 28/28 준비
- 결함 task: Query Crop+same-item Reference Crop+prompt 30/30 schema success, 실패 0. 그러나
  `UNCERTAIN` 26, `NO_VISIBLE_DEFECT` 2, `VISIBLE_DEFECT` 2. 공식 label 대비 TP/FP/TN/FN
  0/2/0/2, positive/negative abstain 각 13, coverage 13.3%로 품질 FAIL
- 결함 판정: detached pump를 관찰하고도 no-defect로 냈고 정상 보충제 용기 두 건은 viewpoint를
  deformation으로 오판. prompt의 관점 차이 금지에도 generic Qwen VLM은 E3/공식 label 대체 불가
- Product 분리: `kaputt_product_metadata/1.0.0`에는 name/category/form/use/usability/evidence만 두고
  condition·defect·price·refund·brand/SKU·business action을 제거. official defect label은 provenance에만
  보존하고 prompt 입력에서 제외
- Product 결과: 30/30 strict schema success·실패 0, specific generic name 25·uncertain 5,
  generic-only/paired 30, 금지 필드·email/phone/currency/long-number 0. latency min 7.4초, p50 8.5초,
  p95 10.0초, max 10.0초
- Visual QA: 임시 5x6 Contact Sheet로 이름 후보를 대조. 머핀 팬·로션·접착제·샴푸/세정 용기 등은
  유용한 후보였으나 supplement/cleaning-chemical/pet-care enum 부재로 category mismatch가 존재.
  25/30은 specificity이며 Human Gold accuracy가 아님
- Artifact: defect result SHA `e53a516b8ffb5400def2f490f3376716e18d89e2029670e6782a14f408deb2a6`,
  product result SHA `7ddc9197c957f9e81b5560476a789f06d555e346ff8dc0df734c076abfef846a`를 private
  `/home/data/datasets/kaputt/derived/csight-qwen38/`에 append-only 보존
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 6 PASS, remote Pydantic 30/30 재검증,
  provenance/task/금지 필드/민감 패턴/Contact Sheet 확인. 전체 Backend/Web 회귀는 미실행
- Runtime: 19:34 KST VLM healthy, GPU 22,731/24,564 MiB, idle 0%, 40°C. 사용자 재기동 지시에
  따라 Container를 중지하지 않고 유지
- Git safety: Commit·Push·PR·현재 PoC Catalog 자동 반영 없음. 사용자 소유 미추적 문서 3개 보존
- 다음 작업: 사람이 30건 product name/category Gold를 확정하고 taxonomy를 승인한 뒤 accuracy를
  계산하며, full Batch 또는 PoC Catalog 반영은 그 이후 별도 결정

### 2026-08-28 — Curated PoC Closed-set v1

- 목표: PoC/MVP 시연 범위를 열린 상품·결함 추론 대신 승인된 상품군 4개·결함군 3개와 점수
  구간으로 고정하고, 해당 조건을 통과한 데이터만 내부 데모에 채택
- 계약: `poc_closed_set/1.0.0`, 상품군은 뷰티·개인관리/식품·건강보조제/생활화학·접착제/
  주방·수납, 결함군은 개봉·분해/변형·파손/표면 손상·누액. E3 runtime threshold
  `0.8984375`는 유지하고 선별 margin만 defect `>=0.95`, reference `<=0.10`으로 설정
- 구현: `app/platform/poc_demo_selection.py`의 기술 독립 registry validator와 admission Gate,
  `evaluation/poc_closed_set_v1/registry.json` 10건 SHA Allowlist, v2 seed source identity·원천 label·
  E3 결과 fail-closed, seed report의 class/admission provenance를 추가
- UI: Case 상세 가상 상품 카드에 `PoC 상품군`, 자연어 `결함 시나리오`, `데이터 사용 기준`을 표시.
  저점수 참고는 `정상`이 아니라 `사람 확인 저점수 참고`로 명시
- 실제 coverage: 기존 10건은 상품군 2/4(`PERSONAL_CARE_CONTAINER`,
  `KITCHEN_OR_STORAGE_ITEM`)와 결함군 3/3을 표현. 나머지 상품군 두 개는 사진이 없어 미검증이며
  Qwen은 후보 제안만 하고 자동 승인·결함 분류에 사용하지 않음
- 검증: 실제 Top-100 package와 normal reference로 identity/rank/SHA/source label 10/10 PASS.
  기존 actual E3 seed 원장의 10건도 새 Gate 10/10 채택, defect 최저 0.9985969·reference 최고
  0.00006098로 각각 0.95/0.10 margin을 통과.
  Ruff PASS, Format 392, Pyright 0, 기본 682 PASS/65 deselected, closed-set 포함 targeted 25 PASS,
  Qwen 보조 도구 6 PASS. Web lint·typecheck·OpenAPI sync·22 files/60 tests·production build PASS,
  `git diff --check` PASS
- Runtime: 20:08 KST Web/API 재배포 뒤 Core 7 healthy, local Web/API health PASS, public Login DOM과
  console error 0. 인증 정보는 입력하지 않아 실제 Case 상세 화면과 live E3 seed 재실행은 미실행
- 안전: E3가 결함 유형을 예측하거나 저점수를 정상 확정한다는 주장 0, 실제 Decision/Action/메일
  발송 0. Commit·Push·PR 없음, 사용자 소유 미추적 문서는 수정·삭제·Stage하지 않음
- 다음 작업: 빈 상품군 두 개의 후보를 각 3~5장 확보해 사람 검수·권리·SHA·E3 score를 승인한 뒤
  `poc_closed_set` 새 버전에 추가하고, MVP 평가는 선별 표본과 분리된 Human Gold로 수행

### 2026-08-28 — Curated PoC 20-case Expansion

- 목표: 기존 최신 10건을 수정하지 않고 서로 다른 이미지·주문·문의 10건을 추가해 내부 시연
  범위를 결함 후보 12건과 사람 확인 저점수 참고 8건, 총 20건으로 확장
- 데이터: 결함 rank 1/9/22/31/73/79와 저점수 참고 rank 1/20/65/67을 사람 육안 대조하고
  exact SHA Allowlist로 고정. 개인 이름이 보이는 defect rank 61과 모호한 rank 56은 제외
- 계약: `realistic-internal-demo-v3`, `CLOSED_SET_EXPANSION_R3`,
  `poc_closed_set/2.0.0`. 기존 v2 10건과 registry v1은 불변이며 두 팩 합계로 상품군 4/4,
  원천 결함군 3/3을 표현. E3 운영 threshold `0.8984375`, 선별 margin `0.95/0.10` 유지
- Runtime: 최초 1건에서 API가 Mock snapshot, Worker가 Remote E3 snapshot인 설정 불일치를 발견.
  실패 Run 두 개는 삭제하지 않고 append-only 보존하고 API를 Worker와 같은 actual E3 identity로
  재구성. 고정 retry-2에서 성공한 뒤 새 10건 최신 Analysis `SUCCEEDED` 10/10
- 멱등성: 첫 완주에서 Case 9 생성/1 재사용, Evidence 9 업로드/1 재사용, 성공 Analysis 10 생성.
  즉시 재실행은 Case·Evidence·Analysis 10/10 재사용, Private Evidence integrity 10/10
- 안전: seed 전후 Policy Retrieval·Grounding·Policy Evaluation·Human Review·Resolution·Intent·
  Simulation Attempt/Result 모두 0. 저점수=정상 주장, 모델 결함 유형 예측, 실제 Decision·Action·메일 0
- UI: 20개 가상 상품/가격대와 closed-set 자연어 label 추가, provenance schema 3.0 fail-closed,
  상담 목록은 오래된 R1 중복을 숨기고 최신 R2 10건+R3 10건을 활성화. Web 재배포 후 local/public
  asset `index-CJlif6d0.js` 일치와 `/web-health` PASS
- 검증: Ruff·Format PASS, Pyright 0, targeted backend 35 PASS, 기본 686 PASS/65 Skip,
  Web lint·22 files/62 tests·production build PASS, v3 seed report replay hash
  `dc9bedb9b5de24a3a49c681b5d519024c6f52fd7791934d536d3a4879a78c8fb`, `git diff --check` PASS
- 범위: 클래스 표현은 정확도·calibration·시장 분포 평가가 아니다. 원본 재배포 권리는 미확인이고
  내부 합성 기술 시연만 허용. Commit·Push·PR 없음, 사용자 소유 미추적 문서 보존
- 다음 작업: 인증 상담원으로 새 상품군 대표 Case를 한 건씩 열어 표시와 Human Review 흐름을
  수동 확인하고, 20건 연속 처리의 메모리·queue·실패율 기준선을 별도로 기록

### 2026-08-28 — Korean Product-first Inquiry Console

- 목표: 상담 목록의 `case-primary`·`case-action` 영역과 상세 화면에서 내부 영문 코드보다 한글
  상품명과 자연어 업무 표현을 우선해 실제 상담원이 빠르게 읽을 수 있도록 정리
- 목록: `Case desk/상담 케이스`를 `문의 목록/접수된 문의`로 바꾸고, 활성 20건은 주문번호 대신
  `플랫케이스 오거나이저 2P` 같은 가상 상품명을 제목으로 표시. 주문번호·상품번호·가격대는
  한글 label이 붙은 보조 정보로 이동
- 업무값: `EXCHANGE/REFUND/RETURN/REPAIR/INFORMATION/OTHER/UNSPECIFIED`를
  교환/환불/반품/수리/정보 안내/기타 문의/아직 정하지 않음으로 표시. 검토 유형·우선순위·필터도
  일반 정책 검토/안전 검토/보통/긴급 등으로 변환하며 API 저장값은 변경하지 않음
- 상세/등록/보고서: 상세 제목을 상품명 우선으로 통일하고 문의 번호·주문 번호·상품 번호를 분리.
  새 문의 select와 버튼, 검토함, 데이터 자산, 운영 지표, 보고서의 영문 eyebrow와
  Resolution/DRY-RUN/Case 문구를 한글 업무 표현으로 교체
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI sync PASS, 22 files/62 tests PASS,
  production build PASS. 검색·처리 요청·모의 실행 요약의 잔여 영문도 제거한 뒤 local/public
  `/web-health` PASS와 배포 asset `index-BLCAsxTA.js` 일치, Core 7개 서비스 healthy
- 범위: CSS class와 API enum은 내부 계약이므로 변경하지 않고 사용자에게 보이는 문자열만 한글화.
  인증 정보는 입력하지 않아 실제 로그인 목록 육안 확인은 미실행. Backend·DB·Decision·Action 변경 0
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지 보존
- 다음 작업: 기존 로그인 세션에서 활성 20건 목록과 대표 상세 1건의 한글 상품명·요청 유형을 육안 확인

### 2026-08-28 — Review Queue Product-name Unification

- 목표: 검토 대기함의 작업 유형 중심 제목을 문의 목록과 같은 상품명 중심 구조로 바꾸고,
  상담 목록·상세에서 `등록 상품 문의`로 보이던 기존 시연/점검 Case도 한글 상품명으로 통일
- 실제 범위 확인: 실행 중 DB를 읽기 전용 조회해 서로 다른 `product_ref` 49종을 확인. 최신
  R2/R3 20종 외에 이전 V1/V2 시연 참조, Kaputt/MLX/Policy/Query 점검 참조가 남아 있었음
- 구현: 최신 카탈로그·이전 참조 alias·내부 점검 참조를 하나의 표시 전용 resolver로 통합.
  검토 대기함은 각 Task의 Case 상세를 tenant API로 조회해 상품명, 검토 유형, 문의 번호를 함께 표시하고
  검토 상세 제목도 같은 resolver를 사용. 문의 목록·상세의 `등록 상품 문의` fallback 제거
- 안전 경계: 상품명은 합성 시연용 표시 metadata일 뿐이며 이미지 라벨, Vision class, 정책 입력,
  가격, 환불 금액, External Action parameter 또는 실제 상품 qualification에 사용하지 않음.
  Backend·DB·Human Decision·Action 변경 0
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 23 files/61 tests PASS,
  current DB 49 product refs mapping coverage PASS, production build PASS. minified JS 500.69 kB에 대한
  Vite 권고 1건은 남았으나 build 실패·기능 오류는 아님. `git diff --check` PASS
- Runtime: 21:33 KST Web 재배포, local/public `/web-health` PASS, 양쪽 asset
  `index-DrYgNQF7.js` 일치, API/Worker/Dispatcher/Web/Postgres/RabbitMQ/MinIO 7개 healthy
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지 보존
- 다음 작업: 기존 로그인 세션에서 문의 목록과 검토 대기함을 나란히 열어 동일 Case가 같은 상품명으로
  보이는지 수동 확인하고, 번들 분할은 화면 기능이 더 늘기 전에 별도 최적화

### 2026-08-28 — Full-width Allow/Deny Review Workspace

- 목표: 담당자가 허용/비허용을 선택하는 검토 상세 화면의 과도한 바깥 여백과 작은 글자·버튼을
  줄이고, 데스크톱 작업 공간을 실제 상담 업무 화면처럼 크게 사용
- 레이아웃: 검토 상세만 기존 1280px에서 최대 1540px로 확장. 좌측 근거와 우측 결정 패널을
  `1.25fr / min 460px`로 배치하고 gap 28px, Card padding 28px 적용. 1280px 이하에서는 한 열로
  전환해 좁은 좌우 열이 생기지 않도록 함
- 가독성: 상품명 제목, 탭, 검토 패킷 definition, 권고/qualification, 근거 기록의 글자·간격을 확대.
  빠른 검토 panel padding 26px, 허용/비허용 버튼 높이 90px, icon 25px, 판단 설명과 준비도 badge 확대
- 반응형: 760px 이하에서는 Card padding 18px, 빠른 검토 20px, 버튼 한 열과 header 세로 배치로
  모바일 overflow 없이 기존 조작 흐름을 유지
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 23 files/61 tests PASS,
  production build PASS. minified JS 500.69 kB 권고 1건은 기존과 동일하며 기능 실패 아님.
  `git diff --check` PASS
- Runtime: 21:45 KST Web 재배포, local/public `/web-health` PASS, 양쪽 JS
  `index-Dxfs6VI-.js`와 CSS `index-DKhElaI1.css` 일치, Core 7개 서비스 healthy
- Browser scope: 연결된 브라우저는 로그인 화면 상태여서 인증 정보 입력 없이 검토 상세 육안 QA는
  실행하지 않음. CSS·component 회귀와 배포 asset까지만 현재 PASS
- Git safety: Commit·Push·PR 없음, Backend·DB·Human Decision·Action 변경 0, 사용자 소유 문서 보존
- 다음 작업: 사용자가 로그인한 뒤 대표 빠른 검토 1건을 열어 1440px 이상 화면에서 좌우 비율과
  첫 화면 내 허용/비허용 버튼 노출을 확인하고 필요하면 폭을 한 차례 미세 조정

### 2026-08-28 — Operator-friendly Policy and Analysis Summary

- 목표: 허용/비허용 검토 첫 화면의 정책 enum, qualification JSON, 영문 기술 용어를 상담원이
  즉시 이해할 수 있는 한글 업무 표현으로 전환
- 정책 권고: `REQUIRES_HUMAN_REVIEW`를 `담당자 확인 후 결정 필요`로 표시하고 추가 자료 필요,
  검토 가능, 적용 정책 없음 상태도 자연어 label로 확장. 정책은 참고이며 담당자가 최종 결정한다는
  설명을 함께 표시
- 분석 상태: raw JSON 대신 문의 내용 분석, 이미지 분석, 문의·이미지 일치 확인, 정책 근거 정합성
  네 항목으로 분리. `MOCK_QUALIFIED`는 `시연용 분석 결과 준비`, `NOT_AVAILABLE`은
  `담당자 확인 필요`로 표시하며 model family/revision은 첫 화면에서 숨김
- 문구 정리: `Grounded explanation`을 `정책 근거 확인 요약`, `immutable snapshot`을
  `변경 방지 기록`, 빠른 검토의 `DRY-RUN`을 `모의 처리 확인`으로 교체. 정책 평가 번호와 매핑
  버전은 삭제하지 않고 접힌 `기술 정보 보기`로 이동
- 안전 경계: presentation-only 변환이며 Packet/qualification snapshot/API/DB/hash와 빠른 검토
  점수·임계치·Human Decision 조건은 변경하지 않음. Mock/미지원 범위를 실제 검증 완료로 승격하지 않음
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 24 files/63 tests PASS,
  production build PASS. minified JS 502.99 kB 권고 1건, `git diff --check` PASS
- Runtime: 22:09 KST Web 재배포, local/public `/web-health` PASS, 양쪽 JS
  `index-s6FnmG0z.js`와 CSS `index-CWAdx66O.css` 일치, Core 7개 서비스 healthy
- Git safety: Commit·Push·PR 없음, Backend·DB·Decision·Action 변경 0, 사용자 소유 문서 보존
- 다음 작업: 인증된 검토 상세에서 네 가지 상태가 한 줄씩 읽히고 기술 JSON이 노출되지 않는지
  육안 확인한 뒤, 규칙/인용/기록 탭의 raw key도 같은 label registry로 후속 정리

### 2026-08-28 — Operational-language Console Cleanup

- 목표: 상담원이 보는 화면과 출력 문서에서 `PoC`, 모의, 시뮬레이션, DRY-RUN, Mock, 데모,
  시연 같은 개발·검증 용어를 제거하고 실제 업무 흐름에 맞는 표현으로 통일
- 화면: 메뉴의 `PoC 지표`를 `운영 지표`, 빠른 검토와 처리 상태를 `처리 사전 확인`, 정책 자료를
  `사내 정책 참고 자료`로 교체. 문의·고객·상품 badge도 온라인 접수/고객 정보/상품 정보로 정리
- 문서/메일: 환불 문서는 `외부 처리 전 확인 문서`, 메일은 `안내 메일 만들기`로 전환. 신규 메일
  제목의 개발 표식을 제거하고, 기존 불변 메일은 저장 원본을 수정하지 않은 채 표시 단계에서 같은
  운영 문구로 정규화
- 데이터 표시: 내부 계약의 `DEMO` 상품·고객 참조와 테스트용 주소 표식은 DB/API 값을 바꾸지 않고
  표시 전용 상품번호·고객번호·주소로 정리. 실제 고객 데이터가 아니라는 안내는 유지
- 안전 경계: API enum, Event, DB schema, hash snapshot, Human Decision 조건은 변경하지 않음.
  실제 카드 취소·환급·교환·SMTP 전송은 계속 0이며 `외부 시스템 미반영`을 화면에 명시
- 검증: Web ESLint·TypeScript·OpenAPI sync PASS, 24 files/63 tests PASS, production build PASS.
  Backend 메일 생성 변경은 Ruff·Format과 관련 unit 15 tests PASS, `git diff --check` PASS
- Runtime: 22:29 KST API/Web 재배포, Core 7개 서비스 healthy. local/public JS
  `index-BdA6eGFX.js`와 CSS `index-CWAdx66O.css` 일치
- 미해결: 연결 브라우저의 인증 상태를 사용하지 않았으므로 실제 상담 케이스·검토·인쇄 화면 수동
  육안 확인은 미실행. 번들 500 kB 초과 권고 1건은 기능 실패가 아니며 후속 최적화 대상
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 로그인한 상태에서 대표 환불 케이스의 상담 상세→빠른 검토→환불 확인서→안내
  메일을 순서대로 열어 잔여 개발 문구와 실제 처리 오해 가능성이 없는지 최종 육안 확인

### 2026-08-28 — Operator Workflow Product Direction and Git Handoff

- 목표: 현재까지 누적된 고객·주문 문맥, 20건 closed set, 상담원 UI, 빠른 검토, 환불 문서,
  안내 메일, 데이터 자산과 운영형 문구 변경을 별도 GitHub 브랜치에 보존하고 방향 전환 이유를 기록
- 방향 문서: `docs/product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`에 초기 기술 검증 목표,
  E3 이진 계약과 Qwen enrichment 한계, 실제 기업 데이터 없이 업무 흐름을 보여줘야 했던 이유,
  Human Decision·명시 입력·외부 시스템 미반영·비식별 데이터 자산 원칙과 다음 승격 조건을 정리
- Git: `feature/scenario-poc-hard-plastic`의 `dfaa373`에서
  `codex/operator-console-product-direction` 생성. 누적 100개 파일, 7,096 additions/309 deletions를
  `c90357d feat: evolve CSight into an operator workflow`로 커밋하고 같은 이름의 원격 브랜치에 Push
- 안전 감사: staged diff의 고신뢰 Secret 패턴 0, 1 MiB 초과 blob 0, `git diff --cached --check`
  PASS. `CSight_MASTER_HANDOFF_2026-08-27.md`, `ecommerce_vibe_coding_cs_automation_market_research.md`,
  `kaputt_best_vision_architecture.md`는 미추적 상태로 보존하고 Commit·Push에서 제외
- 검증: Ruff PASS, Format 392 files PASS, Pyright 0, 기본 Backend 686 PASS/65 deselected,
  Web ESLint·TypeScript·OpenAPI sync·24 files/63 tests·production build PASS. 번들 500 kB 초과 권고
  1건은 기능 실패가 아니며 후속 최적화 대상
- 원격 확인: 22:39 KST `refs/heads/codex/operator-console-product-direction`이
  `c90357da845a522bd3ce8ba8446c39f57139fafe`를 가리키는 것을 확인
- 범위: 새 브랜치와 커밋·Push만 수행. PR 생성, `develop/main` 병합, tag/release, 사용자 소유 문서
  stage는 수행하지 않음
- 다음 작업: GitHub Actions 결과를 확인한 뒤 사용자가 원하면 이 브랜치에서 리뷰용 PR을 생성하고,
  인증 상담원 수동 시나리오 QA와 번들 분할을 별도 후속 커밋으로 진행
