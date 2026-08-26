# Sprint 4B Policy Retrieval

- 일자: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-4b-policy-retrieval`
- Base: Sprint 4A commit `6f3a6671be66351aef431b12fe3d04c4a65ce277`
- Commit: 독립 Closeout PASS 후 이 변경 묶음으로 로컬 기준점 생성 승인
- Push/PR: 수행 금지, 현재 모두 없음
- 범위: corpus ingestion, exact BM25, Qwen dense, exact pgvector cosine, RRF, read-only API

## 완료 체크리스트

- [x] Migration `20260826_0006`와 6개 append-only table
- [x] Manifest/hash/count 기반 normalized JSONL ingestion
- [x] Tenant 2, document version 24, clause 168; 반복 ingestion duplicate 0
- [x] Immutable version content mismatch 차단
- [x] metadata 선필터와 exact BM25 tokenizer/profile
- [x] pinned Qwen3 embedding MPS 실제 qualification, embedding 168
- [x] pgvector exact cosine와 cosine similarity 계약
- [x] versioned weighted RRF, dedupe, stable rank
- [x] principal tenant 기반 read-only LEXICAL/DENSE/HYBRID API
- [x] Dev 80 tune/freeze 후 Test 40 한 번 평가
- [x] cross-tenant/future/retired/wrong-version/duplicate 0, determinism 100%
- [x] provider down: lexical 200, dense/hybrid 503, Core ready 200
- [x] 전체 최종 회귀·migration drift·Docker health 재검증
- [x] CURRENT_STATUS 최종 실측 count와 세션 로그 확정
- [x] 독립 Closeout에서 P0/P1 0과 로컬 Commit 조건 충족

## Profile과 결과

BM25는 `ko_policy_lexical:1.0.0`, k1 1.2/b 0.75다. Dense는 pinned Qwen revision,
1024-d, last-token, normalized MPS다. Hybrid는 `policy_rrf:1.0.0`, k 20, lexical 1.5,
dense 0.5다.

Test Recall@5/10은 BM25 0.700/0.925, Dense 0.7125/0.925, Hybrid 0.700/0.925다.
Test MRR@10은 0.525/0.51625/0.53833이고 nDCG@10은
0.59428/0.59920/0.59841이다. 목표값을 사후 설정하거나 test로 profile을 조정하지 않았다.

## 실제 장애·수정 원장

- Embedding profile과 child vector를 flush 전에 함께 저장한 첫 build는 FK ordering으로 실패했다.
  전체 transaction rollback과 vector 0을 확인한 뒤 profile flush 경계를 추가했다.
- API image 첫 build는 dev-only `httpx2` import 때문에 실패했다. production dependency인 urllib3
  adapter로 교체하고 image/API smoke를 재검증했다.
- Dev evaluation 첫 시도는 결과 directory 생성 순서 오류로 freeze 전 실패했다. directory 생성 후
  dev를 다시 실행했고 Test는 그 뒤 한 번만 실행했다.
- Sprint 4A integration 첫 시도의 dispatcher 환경 간섭은 Sprint 4A closeout 원장에 그대로 남겼다.

## 제한과 다음 작업

합성 168-clause corpus와 Mac MPS baseline이다. Reranker, query builder 실행, grounded explanation,
citation answer, policy decision은 구현하지 않았다. Sprint 4C는 현재 frozen candidate baseline 위에서
reranking과 grounding을 별도로 평가한다.
