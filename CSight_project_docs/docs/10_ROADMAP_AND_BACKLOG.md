# 10. Roadmap and Backlog

## 1. 개발 방식

- 2주 단위 Sprint
- 각 Sprint는 실행 가능한 Increment를 남긴다.
- 세부 범위는 멘토링과 데이터 확보 결과에 따라 조정한다.
- 기술 구현과 고객·데이터 검증을 병렬로 진행한다.

## 2. Sprint 계획

### Sprint 0 — Foundation

목표: 개발 기반과 계약 확정

- 저장소와 디렉터리 구조
- `pyproject.toml`, Ruff, Type Check, pytest
- Docker Compose Core 환경
- PostgreSQL, RabbitMQ, MinIO
- Alembic 초기 Migration
- LLM·Vision Mock Adapter
- CI Pipeline
- ADR 확정

완료 기준:

- Core 서비스가 한 명령으로 실행
- Health Check 통과
- Mock 기반 E2E Skeleton 통과

### Sprint 1 — Case and Evidence

- 로컬·PoC JWT 로그인과 명시적 개발 Identity Seed
- Principal 기반 Tenant Scope와 역할 권한
- Case 생성·목록·상세·상태 이력 조회
- Tenant 단위 Case 생성 Idempotency
- JPEG/PNG/WebP 검증과 Evidence 업로드
- Private MinIO 원본 저장과 Signed URL
- PostgreSQL·MinIO 부분 실패의 `PENDING`/`AVAILABLE`/`FAILED` 보상 전략

완료 기준:

- 인증한 사용자가 Tenant를 Body에 지정하지 않고 `RECEIVED` Case와 최초 이력을 생성
- 목록·상세·Evidence 메타데이터가 자신의 Tenant에서만 조회됨
- 동일 Idempotency Key 재시도로 Case가 중복 생성되지 않음
- 검증된 원본은 DB가 아닌 Private Object Storage에 저장되고 짧은 Signed URL로 접근
- Case/Evidence 접수만으로 Analysis Run이나 LLM·Vision 작업을 시작하지 않음

명시적 후속 범위:

- Evidence 업로드 Idempotency와 Reconciliation/Orphan Cleanup
- EXIF 제거, 재인코딩, 개인정보 마스킹과 보관·삭제 정책
- Refresh Token, OIDC/SSO, PostgreSQL RLS

### Sprint 2 — Async Analysis and LLM

- [x] `product_defect_text_extraction` Pipeline `1.0.0`과 `TEXT_EXTRACTION` Stage
- [x] Append-only Analysis Run/Stage/Attempt와 명시적 상태 전이
- [x] Tenant-scoped Analysis 등록 Idempotency와 Canonical Request Hash
- [x] Run + Stage + Idempotency + `analysis.requested.v1`의 단일 Transaction 등록
- [x] Transactional Outbox Dispatcher, Backoff, Claim/Lease와 Fenced Worker
- [x] 활성 Lease 중복 Delivery의 Lease-expiry Recovery Outbox와 Stale Token Fencing
- [x] 정확히 여섯 ID만 전달하는 Celery/RabbitMQ Task
- [x] Strict LLM 구조화 Schema, Exact Source Quote와 입·출력 상한
- [x] Code Prompt Manifest `1.0.1`, Canonical SHA-256 Content Hash, Injection-safe Rendering과
  Taxonomy·중복 방지 지시
- [x] 결정적 Mock과 OpenAI-compatible vLLM Adapter
- [x] POST/목록/상세 Analysis HTTP API와 역할·Tenant Scope
- [x] 외부 GPU 검증을 기본 Suite에서 분리한 `external_gpu` 경계

### Sprint 2.5 — Qwen3.8 Serving Qualification

- [x] Qwen3.8-27B AWQ INT4 Artifact와 immutable revision 고정
- [x] vLLM image digest, text-only/non-thinking/private authenticated 배포 자산
- [x] 100건 합성 qualification Dataset과 평가기
- [x] 단일 RTX 4090 Cold Start 2회와 20분 이상 Stability
- [x] 안전 Gate와 실제 external GPU 계약·Backend E2E

실제 모델 판정은 `QUALIFIED_WITH_LIMITATIONS`다. 구조·안전 Gate는 통과했지만 Action Accuracy와
Missing Information 품질 한계가 있어 Human Review 없이 업무 결정을 만들 수 없다.

세부 실행 상태와 실제 측정값은 `docs/progress/SPRINT_2_5_QWEN38_SERVING.md`에서 관리한다.
QUALIFIED 판정 전에는 Sprint 2 Mock/Contract 결과를 실제 모델 검증으로 해석하지 않는다.

완료 기준:

- API가 202 응답 후 LLM 구조화 결과를 비동기로 저장
- 동일 요청은 기존 Run을 200으로 재생하고 중복 Run/Stage/Outbox를 만들지 않음
- 실패·재시도·만료 Attempt와 Provider/Model/Prompt/Schema Snapshot을 조회·감사 가능
- Celery Retry가 아닌 PostgreSQL 상태와 Outbox가 재시도·복구의 Source of Truth
- 전체 Prompt, Raw Provider Response, 고객 원문과 Secret이 Outbox/Broker/로그에 남지 않음

설계 결정:

- [ADR-0009: Transactional Outbox와 Fenced Analysis 실행](adr/0009-transactional-outbox-and-fenced-analysis-execution.md)
- [ADR-0010: Code Prompt Registry와 구조화 결과만 보존](adr/0010-code-prompt-registry-and-structured-output-retention.md)
- [ADR-0011: Case와 Analysis Run 수명주기 분리](adr/0011-separate-case-and-analysis-lifecycles.md)
- [ADR-0012: Qwen3.8 고정 Artifact의 Private Text-only 서빙](adr/0012-qwen38-private-text-serving.md)

### Sprint 3 — Vision Contract and Mock Integration

- [x] Canonical Vision Contract와 결정론적 Mock·Remote Adapter
- [ ] 실제 Vision model/dataset/taxonomy/threshold qualification
- [x] 이미지 품질 결과와 Detection 정규화
- [x] Model·taxonomy·threshold·pre/postprocess Version 저장
- [x] LLM·Vision 병렬 실행
- [x] Evidence Reference Allowlist와 Private Object 접근 경계
- [x] Vision Stage/Attempt/Result의 Append-only Schema와 Migration
- [x] Text/Vision 부분 실패와 재개 상태 계약

완료 기준:

- Vision 모델 교체가 Domain 코드 수정 없이 가능
- 부분 실패 상태가 정상 저장

Sprint 3의 기본 경로는 Mock Vision으로 검증됐다. 실제 Vision qualification과 Alignment는 아직
완료되지 않았으며 Sprint 2 Text Extraction Run을 덮어쓰지 않는 별도 Stage/Result 경계를 유지한다.

### Sprint 4~5B — Retrieval, Grounding, Policy, Human Review

- [ ] Alignment v1
- [x] Versioned Policy Corpus와 RAW/HYBRID Retrieval·Top-3 Citation
- [x] Citation-grounded Explanation 구조·allowlist
- [x] Versioned deterministic Policy Evaluator
- [x] Human Review Task·Packet·Claim·자료요청·이관·Resolve
- [x] Append-only Review Action·Assignment·Decision 감사 기록
- [ ] Case Resolution과 External Action `DRY_RUN`
- [ ] 상담원 Web UI, Review Report와 KPI 집계

완료 기준:

- 자료부족·고위험 Case가 서로 다른 Human Review Task로 분기
- 정책 권고와 인증된 사람의 최종 판단을 별도로 보존
- Closeout 전 async crash recovery·fencing·integrity Gate 통과

### Sprint 5C — Resolution and External Action Simulation

- Case 상태와 분리된 CAS Resolution Projection과 append-only Event
- immutable typed External Action Intent
- 입력 완전성 검증; 누락·오류는 `ACTION_NEEDS_INPUT`
- 네트워크를 사용하지 않는 결정론적 `DRY_RUN`; `LIVE` fail-closed
- Review Report snapshot, React 상담원 콘솔과 PoC KPI

완료 기준:

- Case 단위 결정·Resolution·Simulation 이력 조회
- 필수 입력 누락 시 Attempt/Result 0
- `LIVE` side effect 0, 중복 Intent/Result 0
- Case 단위 immutable 보고서와 분자·분모·표본 수가 있는 KPI 조회

### Sprint 6 — Shadow Mode and Mentoring PoC

- Shadow Mode UI 또는 Export
- 상담원 판단 비교
- Override Reason 분석
- 오류 Taxonomy
- ROI Baseline 입력
- 멘토 피드백 반영

완료 기준:

- 실제 또는 시뮬레이션 Case로 End-to-End 평가 리포트 생성

## 3. P0 Backlog

- [x] 프로젝트 Skeleton과 CI
- [x] Case / Evidence Domain
- [x] JWT Identity / Tenant Scope
- [x] PostgreSQL / Alembic
- [x] MinIO Upload
- [x] Case Create Idempotency
- [x] Celery / RabbitMQ Foundation
- [x] LLM Structured Output
- [x] Vision Contract와 Mock/Remote Adapter
- [x] Analysis Run / Versioning
- [x] Transactional Outbox / Fenced Worker
- [x] Analysis HTTP API / Idempotency
- [ ] Alignment v1
- [x] Policy Evaluator
- [ ] Routing Decision
- [x] Human Review
- [x] Human Review Audit Log
- [x] Case / Evidence E2E Test

## 4. P1 Backlog

- [x] 정책 문서 RAG
- [ ] Report Export
- [ ] SSE 상태 알림
- [ ] Dashboard용 집계 API
- [ ] 재촬영 가이드
- [ ] Prompt 관리 UI
- [ ] 모델 비교 재분석
- [ ] Tenant별 Threshold
- [ ] Shadow Mode 비교 화면

## 5. 명시적 미구현 경계

다음 기능은 현재 구현 완료 범위가 아니며 후속 단계에서 별도 계약, Migration, 테스트와
운영 Guardrail을 갖춰야 한다.

- [ ] 실제 Vision qualification과 결함별 평가
- [ ] LLM·Vision Evidence Alignment
- [ ] Case Resolution과 External Action `DRY_RUN`
- [ ] 실제 외부 환불·교환·재배송·수리 실행
- [ ] React 상담원 콘솔
- [ ] Report 생성·Export
- [ ] KPI 집계와 Shadow Mode 비교
- [ ] SSE 진행 Event
- [ ] Terminal Run 수동 Retry/DLQ 운영 API

## 6. P2 Backlog

- [ ] OIDC / SSO
- [ ] PostgreSQL RLS
- [ ] Triton 전환
- [ ] Object Storage Lifecycle 자동화
- [ ] 외부 CRM Connector
- [ ] OpenTelemetry 기반 분산 Trace
- [ ] Cloud / Linux Core 배포
- [ ] Domain Module 추가

## 7. 병렬 사업 검증 Backlog

- [ ] 초기 고객군 인터뷰 대상 5곳 선정
- [ ] CS 업무 담당자 인터뷰 질문 확정
- [ ] 월간 이미지 문의량 Baseline 조사
- [ ] 평균 검토시간과 재검토율 조사
- [ ] 데이터 제공 가능 범위 확인
- [ ] CRM/API 연동 가능성 확인
- [ ] PoC 성공 기준 합의
- [ ] 구축비·구독·건당 과금 가설 비교

## 8. 역할 분담

### 차인택

- FastAPI Backend
- Domain / Application / Adapter 구조
- PostgreSQL / pgvector
- RabbitMQ / Celery / MinIO
- RAG
- vLLM 배포와 연동
- Vision API 통합
- 전체 Integration / Observability

### Vision 담당자

- 상품군과 결함 Taxonomy 협의
- 데이터 수집·라벨링
- Vision 모델 학습·평가
- Export와 전처리·후처리 명세
- Class별 Threshold와 실패 사례 제공

### 공동

- 고객 가설
- PoC 범위
- 정책 데이터
- 평가 Case
- 멘토링 자료

## 9. Definition of Done

- 기능 요구사항 충족
- 테스트와 Type Check 통과
- Migration 포함
- API·Event Contract 문서화
- 실패·재시도·로그 처리
- 개인정보 영향 검토
- 모델·프롬프트·정책 버전 기록
- Demo Scenario 실행 가능

## 10. Sprint 3 완료와 후속 순서

- [x] Canonical Vision schema와 Remote/Mock Adapter
- [x] Evidence Snapshot과 image별 append-only Result/Detection
- [x] Text/Vision fan-out, Stage join, `PARTIAL_SUCCESS`
- [x] 기존 text-only Pipeline 호환
- [x] 외부 Vision opt-in 분리
- [ ] 실제 Vision model/dataset/threshold calibration qualification
- [ ] Evidence Alignment와 Claim↔Detection matching
- [ ] Confidence calibration과 evidence sufficiency
- [x] Policy Engine과 Human Review 정상 업무 경로
- [x] Sprint 5B async reliability Closeout Gate

Alignment는 Sprint 3 결과 계약을 입력으로 하는 다음 단계이며 이번 Sprint에서 점수나 match를
계산하지 않는다. Policy/Approval은 LLM·Vision 모델이 아니라 versioned rule과 Human Review가
소유한다.

## 11. Sprint 4A 완료와 Sprint 4B 경계

- [x] LLM Contract/Prompt v2와 v1 호환
- [x] deterministic completeness/action consistency
- [x] 합성 clause-based Policy Corpus와 version/tenant metadata
- [x] Extraction/Retrieval/Grounding/Injection/Demo Gold와 report
- [x] Policy Document/Clause DB ingestion
- [x] BM25/dense/pgvector/hybrid retrieval와 evaluation
- [x] Grounded RAG 구조 실행과 Policy Engine/Human Review 정상 경로

Sprint 4A는 검색·결정 runtime을 미리 구현하지 않고 Sprint 4B가 측정할 Reference와 Gold를 먼저
고정한다.

## 12. Sprint 4B 완료와 Sprint 4C 경계

- [x] Policy Document/Clause PostgreSQL ingestion과 immutable conflict
- [x] Exact BM25, pinned Qwen embedding, exact pgvector cosine
- [x] Versioned RRF와 principal-scoped read-only API
- [x] Locked Dev 80/Test 40 retrieval baseline
- [x] Qwen3-Reranker-0.6B와 candidate reranking — qualified, no measurable gain
- [x] Policy Query Builder 실행과 immutable Citation Pack
- [x] Grounded explanation/citation validation/unsupported claim 구조 평가

실제 Qwen semantic grounding 성능, Case Resolution, 외부 Action, UI와 Report는 별도 후속
Gate로 남는다.

Sprint 4C-2는 raw/deterministic/LLM query를 동일 frozen retrieval/reranker 경계에서 비교한다.
Sprint 4C-3는 그 뒤 citation pack과 grounded generation을 독립 평가한다.

## Sprint 4C-2 outcome and 4C-3 gate

RAW remains selected because generated queries made no measurable Dev ranking gain; real LLM is
unqualified without the external Qwen endpoint. Sprint 4C-3 may begin citation-pack design, but
grounded generation requires clause allowlists, citation validation, unsupported-claim detection,
injection evaluation, and grounded RAG evaluation.

## Sprint 4C-3A / 4C-3B Split

4C-3A는 Citation Pack, strict grounding schema, deterministic validators, Mock E2E와 구조 평가를
완료했다. 4C-3B는 Local MLX PoC까지 완료했지만 실제 Qwen semantic faithfulness의 승격 Gate는
남아 있다. Sprint 5A/5B에서 versioned Policy Engine과 Human Review 정상 경로를 연결했다.

4C-3B 결과는 Local Runtime/Grounding qualified-with-limitations, RAW Query 유지다. 후속은 같은
pipeline의 Qwen3.8 RTX4090/vLLM 재qualification, 실제 timeout fault injection, Sprint 5A
versioned Policy Engine과 Human Review Gate다.

## Sprint 5A Status and next boundary

Sprint 5A는 versioned structured rule core, source traceability, frozen input, append-only async
evaluation과 synthetic exactness evaluation을 구현했다. Sprint 5B에서 reviewer decision model과
감사 계약을 구현했고, 비동기 reliability Closeout Gate도 통과했다. Evidence Alignment, real
Vision qualification, Qwen3.8 재평가와 LLM rule generation은 여전히 미구현이다.

## Sprint 5B Closeout Gate와 Sprint 5C

Sprint 5B의 정상 Human Review 경로와 durable outbox crash recovery, publish backoff, worker
lease와 late-result fencing, permanent/retry-exhausted 실패 기록, Packet/Decision hash 재검증,
격리 Integration DB와 전체 회귀를 모두 검증해 Closeout을 확정했다.

그 다음 Sprint 5C는 Case 상태와 분리된 Resolution Projection, immutable Action Intent와
External Action `DRY_RUN`을 구현한다. 필수 입력을 LLM/rationale에서 추론하지 않으며 누락 시
`ACTION_NEEDS_INPUT`으로 끝낸다. 실제 외부 실행, Case Closure, Decision amendment, 알림과
Review 단계 입력 보완은 Sprint 5C 범위 밖이다.
