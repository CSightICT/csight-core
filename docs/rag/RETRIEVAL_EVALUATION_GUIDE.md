# Retrieval Evaluation Guide

Dataset `policy_retrieval_v1`은 Dev 80/Test 40으로 잠겼다. Dev에서 16개 BM25 조합과 36개 RRF
조합만 비교했고 다음 profile을 freeze했다.

- BM25: `k1=1.2`, `b=0.75`
- Dense: pinned Qwen3 embedding 1024-d exact cosine
- RRF: `k=20`, lexical weight `1.5`, dense weight `0.5`

Test 40건은 2026-08-26 한 번 실행됐으며 `retrieval_profile_v1.json`의
`test_evaluated=true`가 재실행을 막는 인계 기준이다. `make evaluate-policy-*`는 잠긴 기존 결과의
query count와 metric artifact를 검증·표시하며 test model inference를 다시 실행하지 않는다.

평가는 Recall/Precision@1/3/5/10, MRR@10, nDCG@10, exact coverage, zero/hard-negative/wrong
version/future/retired/cross-tenant/duplicate/determinism, latency와 지정 slice를 기록한다. Profile이나
Gold 오류를 발견하면 기존 파일을 조용히 변경하지 않고 새 version을 만든다.
