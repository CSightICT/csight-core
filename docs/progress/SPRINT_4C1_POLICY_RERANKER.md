# Sprint 4C-1 Policy Reranker

- Date: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-4c1-policy-reranker`
- Base: `4216028 feat: add hybrid policy retrieval baseline`
- Commit / Push / PR: Sprint 4C-1에서 수행 금지, 모두 없음
- Final quality decision: `RERANKER_NO_MEASURABLE_GAIN`
- Model qualification: `QWEN3_RERANKER_QUALIFIED_WITH_LIMITATIONS`

## 완료 체크리스트

- [x] Frozen HYBRID_RRF candidate K 10/20/30/50와 oracle 상한 측정
- [x] Dev만으로 candidate K 20, final K 10 freeze; Test 후보 진단 한 번
- [x] Qwen artifact/config/model card 확인과 revision pin
- [x] `.venv-reranker`, private MPS service, health/models/rerank
- [x] Pair serialization 1.0.0, token 172/178/187/189, truncation 0
- [x] Migration `20260826_0007`, reranker profile 1, ACTIVE execution profile 2
- [x] Technology-neutral Port, Remote/Mock adapters, complete candidate allowlist validation
- [x] `HYBRID_RERANKED`, 기존 mode 보존, no fallback, provider-down 503
- [x] Dev 80 freeze 후 Test 40 한 번, Test 재튜닝 없음
- [x] Candidate mutation/cross-tenant/wrong-version/future/retired/duplicate 0
- [x] Dev 80 deterministic rerun 100%; Test 재호출 없음
- [x] 실제 두 tenant API smoke와 기존 세 mode 회귀
- [x] ADR-0039~0048, RAG guide, manifest, Make commands
- [x] 최종 전체 regression/migration 3경로/Docker gate 수치 확정
- [x] CURRENT_STATUS 최종 수치와 다음 작업 확정

## Candidate와 품질 결과

Dev candidate recall은 K10 0.93125, K20/30/50 0.9375다. Test는 K10 0.925,
K20/30/50 0.9375다. 필터 이후 평균 후보가 약 7개라 K=20 이후 이득이 없다.
K20 oracle MRR@10 1.0, nDCG@10 0.95164는 candidate-contained Gold의 순서 개선 여지는
크지만 candidate recall 0.9375가 절대 상한임을 뜻한다.

Dev Hybrid→Reranked는 MRR 0.56396→0.53688, nDCG 0.61277→0.61181,
Recall@10 0.93125→0.93125다. Locked Test는 MRR 0.53833→0.51250,
nDCG 0.59841→0.59802, Recall@10 0.925→0.925다. Test query 중 nDCG 개선 17,
악화 23, complete Gold가 candidate pool에 없는 query 5다. 이 결과로 profile을 바꾸지 않았다.

## 실제 장애·수정 원장

- Dev 첫 실행은 K20 candidate의 top10을 기존 K10 결과와 직접 비교해 query 35에서 안전
  중단됐다. 기존 K10은 별도 K10 artifact와 대조하고 reranking은 동일 K20 pool과 비교하도록
  수정했다. Dev artifact freeze 전 실패였고 Test는 호출되지 않았다.
- Concurrency 2 qualification에서 tokenizer가 model lock 밖에 있어 `Already borrowed` 500이
  발생했다. Tokenization과 forward 전체를 한 lock으로 묶고 concurrency 2를 재검증했다.
- 첫 API smoke의 문자열 검사가 공개 embedding profile 식별자를 vector로 오인했다. 실제
  response를 확인하고 금지 key를 vector/decision/tenant로 좁혀 재통과했다.

## 제한과 다음 작업

합성 corpus/query, Mac MPS, raw query baseline만 검증했다. 실제 사용자 query, CPU latency,
동시 처리 이득은 검증하지 않았다. Query Builder는 Sprint 4C-2, Citation/Grounded Generation은
Sprint 4C-3이며 Policy Engine/업무 결정은 여전히 범위 밖이다. 다음 Sprint는 negative ranking
결과를 보존하고 raw/deterministic/LLM query 품질을 분리 비교해야 한다.
