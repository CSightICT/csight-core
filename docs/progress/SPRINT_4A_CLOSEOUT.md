# Sprint 4A Closeout Audit

- 일자: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-4a-llm-reference-data`
- Base: Sprint 3 Closeout `330cbdb`
- 판정: `SPRINT_4A_CLOSEOUT=PASS`
- 미해결 P0/P1: 0/0
- 승인된 로컬 Commit message: `feat: add LLM contract v2 and policy reference corpus`
- Push·PR: 금지

## 1. 독립 감사 결론

Sprint 4A 변경은 v1 호환을 유지한 LLM extraction contract v2, append-only v2 child,
합성 Policy Reference Corpus와 고정 평가 자료에 한정된다. Sprint 4B 범위인 DB ingestion,
BM25, embedding, pgvector retrieval, hybrid search와 검색 API는 포함하지 않는다.

코드·계약·데이터·Migration·Docker runtime을 이전 완료 보고와 독립적으로 다시 검증했다.
P0/P1 결함은 없으며, 외부 GPU를 호출하지 않는 기본 회귀가 전부 통과했다.

## 2. 검증 원장

| Gate | 실제 결과 |
|---|---|
| Ruff | PASS |
| Format | PASS — 179 files |
| Pyright | PASS — 0 errors, 0 warnings |
| Fast regression | PASS — 354 passed, 42 deselected |
| Unit | PASS — 294 passed |
| Architecture | PASS — 4 passed |
| Contract | PASS — 50 passed |
| E2E | PASS — 6 passed |
| Core integration 격리 재실행 | PASS — 36 passed, 외부 GPU 5 skipped, 355 deselected |
| Policy build/validate | PASS — Tenant 2, Document 24, Clause 168 |
| Evaluation build/validate | PASS — 160/120/50/30/10 |
| Reference integrity | PASS — broken/duplicate/cross-tenant 0 |
| Stable aggregate hash | PASS — Policy `84de7fe7d2e03c1db76e73c26e960b178a21e58f6218d5f8970dcc152a606e3f`, Evaluation `3376deb542c297f88d09d771e0942bab1c8535ae68fea0711068a28bf33db961` |
| Migration 3경로 | PASS — empty→0005, 0005→0004→0005, 0004→0005 |
| Alembic drift | PASS — 0 |
| Docker runtime | PASS — Core 6 healthy, live/ready 200, queue 0/0 |
| `git diff --check` | PASS |

## 3. Integration 환경 간섭 기록

장기 실행 중이던 실제 Dispatcher와 Integration suite를 동시에 실행한 최초 시도에서
`test_expired_final_attempt_lease_fails_without_provider_or_retry` 1건이 실패했다. 실제
Dispatcher가 테스트가 만든 Outbox row를 먼저 claim하여 테스트 내부 dispatcher 관측값이
`claimed=1, published=0`이 된 것이 원인이었다. 제품 상태 전이, provider 호출, retry 결함은
발견되지 않았다.

API·Worker·Dispatcher만 중지하고 PostgreSQL·RabbitMQ·MinIO를 유지한 격리 재실행은
`36 passed, 5 skipped`로 통과했다. 이후 최신 image로 Core 6개를 다시 기동해 모두 Healthy와
queue ready/unacked 0/0을 확인했다. 이 실패를 삭제하거나 성공으로 바꾸지 않고 환경 간섭
증거와 격리 재검증을 함께 보존한다.

## 4. 데이터와 Migration

- Corpus source hash: `8e60f4ce869ba83288ac094ba09465481a9d2e431cfe45a7ac4de4114092c237`
- Policy: Tenant 2, Document 24, Clause 168, Policy Type 9, Active/Retired 18/6
- Evaluation: Extraction 160, Retrieval 120, Grounding 50, Injection 30, Demo 10
- Gold missing 0, cross-tenant violation 0, exact/near duplicate 0
- UUID 기반 임시 DB 세 개는 검증 종료 trap으로 삭제했다.
- Container Alembic autogenerate check는 새 upgrade operation 0이었다.

## 5. 제한사항

- 합성 Corpus는 실제 기업 정책이나 법률 자문이 아니다.
- 실제 Qwen extraction 평가는 실행하지 않았고 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`이다.
- Gold self-check는 실제 모델 품질 평가가 아니다.
- Retrieval/index/embedding/RAG 실행 경로는 Sprint 4A에 없다.
- 실제 Vision 자산 미제공 skip은 기존 제한으로 유지된다.

## 6. Commit 경계 체크리스트

- [x] P0/P1 미해결 0
- [x] 정적 검사·전체 회귀·Integration 격리 재실행 통과
- [x] 데이터 결정성·참조 무결성 통과
- [x] Migration 세 경로·drift 0·최종 Docker health 통과
- [x] Sprint 4A 범위 밖 Sprint 4B 구현 없음
- [x] `kaputt_best_vision_architecture.md` 수정·삭제·Stage 금지
- [ ] 승인된 Sprint 4A 파일만 Stage 후 범위 재감사
- [ ] 정확한 message로 로컬 Commit 생성
- [ ] Commit SHA를 다음 Sprint 인계 문서에 기록

## 7. 다음 작업

승인된 Sprint 4A 범위만 로컬 Commit한 뒤 그 Commit에서
`feature/sprint-4b-policy-retrieval` 브랜치를 생성한다. Sprint 4B는 DB schema/ingestion부터
시작해 exact BM25, 실제 고정 Qwen embedding, pgvector exact cosine, versioned RRF, API와
locked dev/test 평가 순서로 진행한다.
