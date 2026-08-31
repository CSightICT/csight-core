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

This exact profile is now a frozen Shadow baseline, not an automatically active
product release. From the repository root, run:

```bash
make verify-qwen4090-candidates
make audit-qwen4090-hub
make require-qwen4090-release
```

The first command validates the candidate matrix and frozen evaluation-data digest. The second
audits the exact upstream metadata. The final command is the release gate and intentionally returns
a failure while no candidate has complete provenance plus current 4090 qualification evidence.
None of these commands starts, stops, downloads, or activates a model.

The Hub audit is an online metadata gate. It checks every exact revision, license, base-model
lineage, LFS identity, and safetensors byte count without downloading model weights. The live host
preflight remains authoritative for the bytes actually staged on the RTX 4090 node.

The actual synthetic extraction sequence is documented in
[`QWEN4090_QUALIFICATION_GUIDE.md`](../../docs/llm/QWEN4090_QUALIFICATION_GUIDE.md). It uses
repeatable Dev, digest-verified freeze, and a single sealed Test. Run it on the GPU host when its
`nvidia-smi` memory samples are intended as release evidence.

`make verify-qwen4090-compose-profiles` checks both runnable Shadow overlays against the frozen
matrix. `make start-qwen4090-candidate QWEN4090_CANDIDATE_ID=...` accepts only the vLLM 0.28.0
27B Runtime Challenger or official 8B FP8 Model Challenger, waits for health, then requires the
authenticated `/v1/models` response to contain exactly the selected alias. These profiles remain
Shadow-only and do not update Core configuration or model activation state.
