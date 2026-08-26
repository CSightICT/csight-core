# Sprint 4A — LLM Contract v2와 Reference Data

- 일자: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-4a-llm-reference-data`
- Base: Sprint 3 Closeout `330cbdb`
- Migration: `20260826_0005`, previous `20260826_0004`
- Closeout: `SPRINT_4A_CLOSEOUT=PASS`, 미해결 P0/P1 0
- 승인된 로컬 Commit message: `feat: add LLM contract v2 and policy reference corpus`
- Push·PR: 수행하지 않음

## 1. 구현 범위

- v1 Pipeline/Prompt/Schema/Result 보존과 v2 `2.0.0/2.0.0/2.0` 추가
- 복수 extracted action과 exact quote, text ambiguity strict schema
- Backend completeness/action consistency rule `1.0.0`
- append-only `llm_extraction_results_v2` child와 명시적 API projection
- Query Builder/Grounded Explanation design-only Prompt `1.0.0`
- clause 중심 합성 Policy Corpus v1과 version/parent/tenant validation
- 고정 Gold datasets, manifest/hash, coverage/quality report와 Make commands

Embedding, BM25, pgvector index, retrieval/RAG API, reranker, Policy Engine, Alignment, Routing,
Human Review, Report와 Vision 변경은 구현하지 않았다.

## 2. LLM Contract v2

| 항목 | v1 | v2 |
|---|---|---|
| Pipeline | `1.0.0` | `2.0.0` |
| Prompt | `1.0.1` | `2.0.0` |
| Schema | `1.0` | `2.0` |
| Requested action | 단일 값 | 명시적 복수 list + exact quote |
| Missing | 혼합 field | text ambiguity / backend missing 분리 |
| Persistence | 기존 table | 별도 append-only child |

Prompt v2 hash는 `3744ecf885e6a3357ffdefd3a8f65e913f501dd43573bcf9d7ff518496fc2d6a`다.
Application rule은 order/product ref, AVAILABLE image count, declared/extracted actions만 사용한다.

## 3. Policy Corpus v1

> 모든 문서는 `SYNTHETIC_REFERENCE`이며 실제 기업 정책이나 법률 자문이 아니다.

| Metric | 값 |
|---|---:|
| Tenant | 2 |
| Document | 24 |
| Clause | 168 |
| Policy Type | 9 |
| Active / Retired | 18 / 6 |
| Exception | 48 |
| Evidence Requirement | 48 |
| Exact / Near duplicate | 0 / 0 |

Corpus source hash는 `8e60f4ce869ba83288ac094ba09465481a9d2e431cfe45a7ac4de4114092c237`다.

## 4. Evaluation Data

| Dataset | Dev | Test | Total |
|---|---:|---:|---:|
| Extraction v2 | 120 | 40 | 160 |
| Retrieval v1 | 80 | 40 | 120 |
| Grounding v1 | 40 | 10 | 50 |
| Injection v1 | 20 | 10 | 30 |
| Demo Pack | - | - | 10 |

Gold clause missing 0, cross-tenant Gold violation 0, broken parent/reference 0이다. Reference
self-check는 데이터·평가기 계약 검증이며 실제 Qwen 평가가 아니다.

## 5. Prompt Registry

| Prompt | Version | Hash |
|---|---|---|
| Text Extraction | 2.0.0 | `3744ecf885e6a3357ffdefd3a8f65e913f501dd43573bcf9d7ff518496fc2d6a` |
| Policy Query Builder | 1.0.0 | `af8a77d4aecad62dcea3056cb2f83bb7619f7bcfbcdd18d8dfba997939c27701` |
| Grounded Explanation | 1.0.0 | `fd27e7c0735b0163387a52c96e7188f5e9b3eb32bb78f45452299f95d9ceb823` |

## 6. 실제 검증 원장

- LLM v2/Corpus Unit focus: PASS — 21 passed
- Sprint 4A Contract focus: PASS — 5 passed
- Policy build/validate: PASS — 24 documents, 168 clauses
- Evaluation build/validate: PASS — 370 records 총합, Demo 포함
- Gold reference/tenant validation: PASS — missing 0, cross-tenant 0
- Stable build: PASS — Policy·Evaluation aggregate hash가 반복 Build 전후 동일
- Static: PASS — Ruff, 179-file Format, Pyright 0 errors·warnings
- Fast regression: PASS — 354 passed, 42 deselected
- Target suites: PASS — Unit 294, Architecture 4, Contract 50, E2E 6; 중복 포함
- Core integration: PASS — 36 passed, external GPU 5 skipped, 355 deselected
- External defaults: SKIPPED — GPU 5 skipped·391 deselected, Vision 1 skipped·395 deselected
- Migration: PASS — empty→0005, 0005→0004→0005, 0004→0005, drift 0, 임시 DB 0
- Final runtime: PASS — 최신 image의 Core 6개 Healthy, live/ready 200, analysis queue 0/0
- Live v2 Mock: PASS — `SUCCEEDED`, actions 2, `MULTIPLE_EXTRACTED`, rule `1.0.0`
- Live cleanup: PASS — 합성 Case/Run 관련 row 제거, analysis queue 0/0
- 초기 stale Docker image Migration: FAIL — image가 `0005`를 포함하지 않아 DB not-up-to-date;
  image rebuild 후 수정·재검증
- 초기 live Dispatcher 동시 Integration: FAIL 1 — 실제 Dispatcher가 테스트 Outbox를 선점;
  API·Worker·Dispatcher 격리 후 36 passed/5 skipped, 최종 Core 6개 재기동·Healthy
- `git diff --check`: PASS

## 7. 선택적 Qwen 평가

`SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`. 현재 Core는 network-free Mock 기본값이며 Sprint 4A에서
Qwen dev/test를 실행하지 않았다. Gold self-check를 실제 모델 결과로 표현하지 않는다.

## 8. 알려진 제한사항과 Sprint 4B 준비도

- 합성 Corpus로 실제 기업 정책·법률 효력을 검증하지 않았다.
- Retrieval/index/embedding/BM25/hybrid/reranker/RAG 실행은 미구현이다.
- Policy Document/Clause DB ingestion은 아직 없고 JSONL artifact만 준비됐다.
- Sprint 4B는 stable Clause, tenant/version/effective filter와 Retrieval Gold가 준비됐으므로
  DB schema→ingestion→BM25 baseline→dense embedding→pgvector→hybrid evaluation 순서로 진행한다.

## 9. 완료 체크리스트

- [x] Sprint 3 로컬 Commit `330cbdb`, Push/PR 없음
- [x] Sprint 4A 전용 Branch, Sprint 4A Commit 없음
- [x] v1 호환과 v2 strict schema/prompt/persistence/API
- [x] deterministic completeness와 action consistency
- [x] 합성 Corpus 최소 규모·버전·tenant·parent 기준 충족
- [x] 다섯 평가 artifact와 manifest/hash/report
- [x] Gold broken/cross-tenant validation
- [x] 전체 Ruff/Format/Pyright/Regression/Integration 최종 Gate
- [x] 격리 Migration 3경로와 최종 Docker Health
- [x] `CURRENT_STATUS.md` 최종 인계와 append-only session log
- [x] 독립 Closeout 감사와 P0/P1 미해결 0
- [ ] 승인된 Sprint 4A 범위만 로컬 Commit하고 SHA를 Sprint 4B 인계에 기록
