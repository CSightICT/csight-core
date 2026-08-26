# Reranker Evaluation Guide

The immutable dataset is `policy_retrieval_v1` (Dev 80, Test 40). Do not change the Sprint 4B corpus,
Gold, BM25, embedding or RRF profile. Candidate analysis measures K 10/20/30/50 and an oracle that
places candidate-contained Gold first. Oracle values are diagnostic upper bounds, not search results.

Dev selected the smallest K at maximum candidate recall: K=20; final K=10. Freeze
`candidate_pool_profile_v1.json`, `reranker_profile_v1.json` and
`retrieval_execution_profile_v2.json` before Test. Test is called once; later deterministic checks
may rerun Dev only.

Every evaluation must verify candidate-set equality before/after reranking; unknown, duplicate,
missing, cross-tenant, wrong-version, future and retired candidates must remain zero. Compare
HYBRID_RRF, HYBRID_RERANKED and ORACLE_UPPER_BOUND at Recall 1/3/5/10, MRR@10, nDCG@10, exact
coverage 5/10, hard-negative rate and latency. Slice by tenant, policy/defect type, relevant count,
parent/exception, version resolution, evidence requirement, escalation and hard negatives.

Current locked result is `RERANKER_NO_MEASURABLE_GAIN`: Test MRR 0.53833→0.51250, nDCG
0.59841→0.59802 and Recall@10 0.925→0.925. Preserve this negative result; do not tune against Test.
