# Qwen3.8 Policy Query Builder Manifest

- Purpose: decision-free structured policy query planning
- Provider family: existing OpenAI-compatible vLLM adapter
- Intended artifact: Qwen3.8-27B deployment configured by Core
- Prompt: `policy_query_builder:1.1.0`
- Input schema: `1.0`
- Output schema: `1.0`
- Sampling: deployment configuration; thinking and preserved reasoning disabled
- Maximum queries: 3
- Raw customer message: excluded by default
- Raw prompt/response/reasoning persistence: prohibited
- Hard filters: prohibited in provider output
- Silent deterministic fallback: prohibited
- Current qualification: `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` on 2026-08-27

The local Mock adapter validates orchestration only and is not model-performance evidence.
