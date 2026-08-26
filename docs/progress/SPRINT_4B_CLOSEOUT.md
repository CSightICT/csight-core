# Sprint 4B Closeout Audit

- 감사 일자: 2026-08-26 (Asia/Seoul)
- 감사 브랜치: `feature/sprint-4b-policy-retrieval`
- 기준 Commit: `6f3a6671be66351aef431b12fe3d04c4a65ce277`
- 승인된 Commit message: `feat: add hybrid policy retrieval baseline`
- Push / PR: 수행하지 않음
- 판정: `SPRINT_4B_CLOSEOUT=PASS`

## 감사 결론

P0 미해결 0, P1 미해결 0이다. Sprint 4B는 immutable corpus ingestion, exact BM25,
pinned Qwen dense embedding, metadata-filtered exact cosine retrieval, weighted RRF와
principal-scoped read-only API를 구현 범위대로 제공한다. Reranker, Query Builder,
Grounded Generation 및 Policy Decision은 포함하지 않는다.

요청된 `PROJECT_BLUEPRINT.md`와 루트 `docs/03_...10_...` 경로는 저장소에 없었다.
Canonical 설계 문서는 `CSight_project_docs/docs/03_...10_...`에 있으며 해당 파일과
Accepted ADR-0026~0038을 감사했다. 이 경로 차이는 현재 동작을 막지 않는 문서 공백으로 남긴다.

## 집중 감사 결과

### Immutable ingestion

- 실제 DB: tenant 2, document version 24, clause 168, embedding 168, tenant별 ACTIVE index 1.
- 동일 corpus hash 재적재는 run `252afd4b-05be-41aa-a961-ac42d91388fa`를 재사용했고
  document/clause 중복을 만들지 않았다.
- 동일 document ID/version/hash는 no-op이고 다른 hash는 conflict로 차단한다.
- document version을 수정하는 repository API가 없고 content mismatch는 fail-closed다.
- parent는 tenant/document/version 복합 경계 안에서 검증되며 missing parent는 0이다.
- retired/future-effective 문서는 metadata filter 이후 후보가 되지 않는다.

### Exact BM25와 Hybrid

- `app/adapters/retrieval/bm25.py`는 Robertson BM25의 IDF와 length normalization을 직접
  계산하며 PostgreSQL `ts_rank`를 BM25로 사용하지 않는다.
- Tokenizer는 NFKC/lower, Hangul bigram과 stable clause identity tie-breaker를 사용한다.
- Frozen lexical profile은 `ko_policy_lexical:1.0.0`, `k1=1.2`, `b=0.75`다.
- Hybrid는 raw score를 더하지 않고 RRF `k=20`, lexical `1.5`, dense `0.5`를 적용한다.
- Dedupe key는 clause의 versioned identity를 보존하고 동일 후보는 한 번만 반환한다.

### Dense retrieval

- Artifact/revision은 `Qwen/Qwen3-Embedding-0.6B` /
  `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`로 고정돼 있다.
- 실제 MPS 응답은 1024-d, last-token pooling, L2 normalization이며 external contract가
  이를 검증했다.
- Query instruction hash와 passage serialization template hash가 frozen profile에 있다.
- NaN/Inf, unit norm, dimension mismatch를 경계에서 거부하며 DB mismatch는 0이다.
- pgvector exact cosine query는 tenant/status/effective/allowlisted metadata filter 뒤에 수행된다.

### API와 장애 격리

- Tenant는 JWT principal에서만 결정되고 request body에서 받지 않는다.
- Embedding service 중단 상태에서 LEXICAL 200, DENSE/HYBRID 503
  `EMBEDDING_PROVIDER_UNAVAILABLE`, Core readiness 200을 실제 API로 확인했다.
- 응답에 tenant ID, vector, 내부 profile ID, policy decision/approval이 없다.

### Locked evaluation

- Dev 80에서 profile을 선택한 뒤 Test 40을 한 번 실행했고 `test_evaluated=true`다.
- Corpus hash: `8e60f4ce869ba83288ac094ba09465481a9d2e431cfe45a7ac4de4114092c237`.
- Retrieval dataset hash:
  `40d6072594328ed4b8d11d359a897e8141365665e6d99ec38b3b169c0ded1e68`.
- Test Hybrid Recall@10 0.925, MRR@10 0.538333, nDCG@10 0.598412다.
- Cross-tenant, wrong-version, future, retired, hard-negative, duplicate 위반은 모두 0이고
  deterministic ranking은 100%다.

## 최종 검증 원장

| 검사 | 실제 결과 |
|---|---|
| Ruff | PASS |
| Ruff format | PASS, 210 files |
| Pyright strict | PASS, 0 errors/warnings |
| Fast regression | PASS, 376 passed, 48 deselected, 31 warnings |
| Unit | PASS, 306 passed, 17 warnings |
| Architecture | PASS, 6 passed |
| Contract | PASS, 58 passed, 1 deselected, 6 warnings |
| E2E | PASS, 6 passed, 8 warnings |
| Core integration | PASS, 41 passed, 5 external GPU skipped, 378 deselected |
| Policy persistence integration | PASS, 5 passed |
| DB invariants | PASS, 2/24/168/168, ACTIVE index 2, mismatch 0 |
| Idempotent ingestion | PASS, run reused, document 24, clause 168 |
| External embedding | PASS, 1 passed, 423 deselected, MPS |
| Two-tenant API smoke | PASS, 6 mode/tenant combinations |
| Provider-down semantics | PASS, LEXICAL 200, DENSE/HYBRID 503, ready 200 |
| Evaluation artifact verifier | PASS, Dev 80/Test 40, test locked |
| Migration | PASS, empty/previous/round-trip to `20260826_0006` |
| Migration drift | PASS, all three paths report no operations |
| Docker health | PASS, Core 6 services healthy |
| `git diff --check` | PASS |

## 미해결·제한사항

- P0: 0.
- P1: 0.
- 합성 168-clause corpus와 Mac MPS qualification만 수행했다.
- Process supervisor와 embedding concurrency 2는 검증하지 않았다.
- `PROJECT_BLUEPRINT.md`는 저장소에 존재하지 않는다.
- Reranker와 이후 생성 단계는 Sprint 4C에서 별도 profile/evaluation으로 다룬다.

## 인계 체크리스트

- [x] Sprint 4B diff와 코드 경계 감사
- [x] 실제 DB/ingestion/retrieval/API/evaluation 재검증
- [x] External Qwen embedding contract 재검증
- [x] Migration 세 경로와 drift 재검증
- [x] Core 6개 서비스 healthy 복구
- [x] `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage 확인
- [ ] 승인된 Sprint 4B 파일만 로컬 Commit
- [ ] Commit SHA를 다음 Sprint 상태 문서에 기록
- [ ] Sprint 4C-1 전용 브랜치 생성

다음 작업은 Sprint 4B Commit에서 `feature/sprint-4c1-policy-reranker`를 생성하고,
reranker 구현 전에 frozen HYBRID_RRF 후보 K 10/20/30/50의 recall과 oracle upper bound를
Dev에서 측정하는 것이다.
