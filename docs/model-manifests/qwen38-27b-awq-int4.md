# Qwen3.8-27B AWQ INT4 Model Manifest

- Manifest status: `QUALIFIED_WITH_LIMITATIONS`
- Recorded: 2026-08-26 (Asia/Seoul)
- Evaluation dataset: `qwen38_qualification_v1`

## Identity and provenance

| Field | Value |
|---|---|
| Model family | `Qwen3.8-27B` |
| Model artifact | `cyankiwi/Qwen3.8-27B-AWQ-INT4` |
| Artifact revision | `63768c10df38c0395e12ef49edac1bd539eaeeea` |
| Served model name | `csight-qwen3.8-27b` |
| License | Apache-2.0 |
| Artifact size | 21,041,255,795 bytes |
| Architecture | `Qwen3_5ForConditionalGeneration` / `qwen3_5` |
| Quantization | `compressed-tensors`, packed INT4, group size 32, asymmetric |
| Calibration | Artifact publisher does not document the calibration dataset in the model card; unknown |

The artifact is a Community quantization rather than an official Qwen release artifact. Several
visual and linear-attention modules are excluded by its quantization config. The qualified service
therefore pins the exact revision and measures the deployed artifact rather than inferring quality
from the base model.

## Qualified runtime profile

| Field | Value |
|---|---|
| vLLM | `0.26.0`, image digest `sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52` |
| Transformers | `5.14.1` |
| PyTorch | `2.11.0+cu130` |
| CUDA runtime | 13.0 |
| NVIDIA driver | 580.173.02 |
| Hardware | Single NVIDIA GeForce RTX 4090, 24,564 MiB |
| Serving mode | Text-only via `--language-model-only` |
| Max context | 8,192 tokens |
| Max sequences | 1 |
| KV cache | FP8 |
| Execution | Eager; no CPU offload |
| Thinking | Disabled at server and request level |
| Structured output | OpenAI-compatible strict JSON Schema, Pydantic validation, exact source quotes |
| Network | Private Tailscale bind, authenticated with environment-injected API key |

## Reproducible serve command

The runtime secret is supplied only through `VLLM_API_KEY`; it is intentionally absent from the
command line.

```bash
vllm serve cyankiwi/Qwen3.8-27B-AWQ-INT4 \
  --revision 63768c10df38c0395e12ef49edac1bd539eaeeea \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name csight-qwen3.8-27b \
  --language-model-only \
  --max-model-len 8192 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.95 \
  --kv-cache-dtype fp8 \
  --enforce-eager \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs \
    '{"enable_thinking":false,"preserve_thinking":false}'
```

The container port is published only on the node's private address. The apparent container command
host `0.0.0.0` does not create a public host bind; `compose.llm.yml` controls the restricted publish.

## Qualification measurements

| Metric | Result |
|---|---|
| Initial download-to-ready | 11m57s wall time including one security-driven stop/key rotation; download alone was not isolated |
| Cold start 1 | 8m06s from restart to API ready with remaining download; model load 402.08s |
| Cold start 2 | 97s cache-hit to API ready; weight load 7.14s, engine init 39.41s |
| First structured warm-up | 4.43s total |
| Idle / peak VRAM | 23,009 MiB initial idle / 23,825 MiB under and after workload |
| KV cache allocation | 3.48 GiB, 65,536 tokens; weights 18.36 GiB |
| Profile A TTFT p50 / p95 | 0.089s / 0.176s |
| Profile A latency p50 / p95 | 1.470s / 1.558s |
| Profile A output rate | 36.36 output token/s |
| 20-minute stability | PASS — 26m19s, restart 0, OOM 0, error/traceback 0 |
| Quality and safety gates | PASS after Prompt 1.0.1 — 100 cases |

### Quality baseline

| Metric | Result |
|---|---:|
| JSON Schema / Pydantic / exact quote | 100% / 100% / 100% |
| Forbidden field / injection violation / reasoning leakage | 0% / 0% / 0% |
| Issue type precision / recall / F1 | 0.95 / 0.95 / 0.95 |
| Requested action accuracy | 0.23 |
| Missing information precision / recall / F1 | 1.00 / 0.00 / 0.00 |
| UNKNOWN usage | 0.10 |
| Mean output tokens | 57.23 |

The original Prompt 1.0.0 produced duplicate issue types in two deterministic multi-defect cases,
so Pydantic validity was 98%. vLLM 0.26.0 rejected JSON Schema `uniqueItems` as an unimplemented
grammar key. Prompt 1.0.1 added explicit taxonomy and set semantics; the same 100 cases then passed
all safety gates and improved issue F1 from 0.594 to 0.95. No validator or gate was weakened.

## Known limitations

- Single-GPU 24GB headroom is extremely small: workload peak was 23,825 MiB and observed free memory
  fell as low as 254 MiB. Context and concurrency increases require requalification.
- FP8 KV cache can reduce accuracy if scaling is suboptimal; the measured baseline is authoritative.
- Eager execution trades throughput for predictable memory behavior.
- The Community artifact's calibration data is not documented in its model card.
- The 100-case qualification dataset is synthetic and cannot establish production-domain accuracy.
- Requested-action accuracy 0.23 and missing-information F1 0.00 prohibit treating the extraction as
  an autonomous workflow decision. Versioned policy and human review remain mandatory.
- Concurrency 2 was stable but doubled p50 latency and TTFT because max sequences remains 1; the
  initial production profile serializes work through the Celery queue.
- No Qwen vision feature, CPU offload, fallback model, autoscaling, or fine-tuning is included.
