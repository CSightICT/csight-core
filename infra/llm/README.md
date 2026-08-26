# Qwen3.8 private inference node

This directory pins the text-only CSight deployment of
`cyankiwi/Qwen3.8-27B-AWQ-INT4`. The Compose service is deliberately separate
from Core: an LLM outage must not affect Core readiness.

## Safety boundary

- Bind only to the GPU node's private Tailscale address. Never use `0.0.0.0` as
  `LLM_BIND_ADDRESS`.
- Authentication is mandatory. Real keys belong only in an untracked runtime
  env file and are passed through `VLLM_API_KEY`, never a process argument.
- The artifact revision and vLLM image digest are immutable in Compose.
- `--language-model-only` prevents loading the multimodal encoder for this
  text-only use case. Qwen vision is not a CSight defect detector.
- Thinking is disabled at both server and request level. Raw prompts, responses,
  and reasoning must not be persisted.

## Start and verify

1. Copy `.env.llm.example` to an untracked `.env.llm` on the GPU node.
2. Replace the private bind address and generate a long random API key.
3. Run `bash serve_qwen38.sh .env.llm`.
4. From an authorized private client, export `LLM_BASE_URL` ending in `/v1` and
   `LLM_API_KEY`, then run `bash healthcheck.sh`.

The qualified default is one sequence with an 8,192-token context. Increase
concurrency or context only after rerunning cold-start, stability, quality, and
performance qualification. See the model manifest and Sprint 2.5 progress log
for measured results and limitations.
