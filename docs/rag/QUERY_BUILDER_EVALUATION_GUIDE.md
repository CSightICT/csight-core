# Query Builder Evaluation Guide

1. Run the external Extraction v2 qualification. If no real Qwen endpoint is configured, record
   `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Mock is contract-only.
2. Build and validate `policy_query_builder_v1`. Confirm Dev 80, sealed Test 40, stable hash, no
   legacy query-text overlap, valid active references, and no cross-tenant Gold.
3. Compare RAW, deterministic, and real LLM on Dev using the unchanged HYBRID profile. Do not enable
   the reranker. Soft hints remain unapplied for profile 1.0.0.
4. Freeze query-builder and retrieval execution profiles. Run Test once without reconfiguration.
5. Report direct schema/purpose/hint/security metrics and downstream Recall, MRR, nDCG, exact
   coverage, hard negatives, version/tenant correctness, determinism, and latency.
6. Report Gold and Model Extraction separately. If external Qwen is absent, Model Extraction and LLM
   strategy cells remain Skipped rather than being filled with Mock results.

The existing `policy_retrieval_v1` Test is regression-only. A Test result must never trigger prompt,
rule, query-count, fusion, or soft-hint changes.
