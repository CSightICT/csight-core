# Grounding Evaluation Guide

1. Validate the existing synthetic `rag_grounding_v1` 50 and `prompt_injection_v1` 30 records.
2. Run `make evaluate-grounding-contract` for deterministic schema, allowlist, coverage, tenant,
   version, duplicate, forbidden-decision, injection, and replay metrics.
3. Treat Mock generation as orchestration and contract evidence only.
4. Keep semantic citation precision/recall, unsupported policy claim rate, and paraphrase
   faithfulness as `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` until the pinned Qwen endpoint is available.
5. When a real endpoint becomes available, tune only on Grounding Dev 40 and Injection Dev 20,
   freeze prompt/model/profile hashes, then access each sealed Test 10 split once.
6. A valid Citation ID does not prove semantic support. Report structural and semantic outcomes
   separately and never infer a policy or business decision from either score.
