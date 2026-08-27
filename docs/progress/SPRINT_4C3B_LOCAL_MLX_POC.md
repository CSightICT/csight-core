# Sprint 4C-3B — Local MLX LLM PoC

Status: `LOCAL_MLX_POC_QUALIFIED_WITH_LIMITATIONS` / `RAW_REMAINS_SELECTED` / `LOCAL_GROUNDING_POC_QUALIFIED_WITH_LIMITATIONS`
Branch: `feature/sprint-4c3b-local-mlx-grounding`
Base commit: `72cbe12 feat: add citation grounding guardrails`
Commit/Push/PR: intentionally not performed.

## Completed checklist

- [x] Exact public artifact and immutable revision verified and downloaded.
- [x] Isolated Python 3.12 MLX environment; native localhost server; Docker host bridge.
- [x] Mock and vLLM retained; MLX added behind the existing port.
- [x] Thinking disabled; strict JSON Schema; no regex repair or silent fallback.
- [x] Extraction Dev120, prompt freeze, sealed Test40 once.
- [x] Query Builder Dev80, profile freeze, sealed Test40 once; RAW remains selected.
- [x] Grounding Dev40 + Injection20, prompt freeze, sealed Test10 + Injection10 once.
- [x] Human semantic spot-check Dev20 + all Test10.
- [x] Docker-based safe-default E2E 10/10 with duplicate and citation checks.
- [x] More than 20 minutes continuous stability (observed 2h34m), RSS about 6.50 GB, swap 0.
- [x] Core six services healthy while MLX and embedding services ran natively.
- [x] Cross-tenant read of an actual Local MLX grounded result returned 404.
- [x] Unreachable Local MLX endpoint mapped to retryable `LLM_PROVIDER_UNAVAILABLE` with provider
  `mlx`; Core readiness stayed 200 and no Mock fallback occurred.
- [ ] Actual timeout-to-recovery transition and actual malformed-provider server were not injected; offline contract coverage exists.
- [ ] Experimental LLM-query full HTTP E2E was not promoted because RAW remained selected.

## Results

Extraction was structurally safe but weak on requested actions and ambiguity. Query plans were structurally safe after freeze, but Test Recall@10 was 0.90 versus RAW 0.975 and exact coverage was 0.75 versus 0.85. Grounding final Dev/Test automatic metrics and the 30-record human spot-check passed, but the synthetic corpus is deliberately simple.

Actual HTTP E2E succeeded for 10 fresh cases through API, Outbox, RabbitMQ, Docker Celery Worker, Local MLX Extraction, RAW Hybrid retrieval, immutable top-3 Citation Pack, Local MLX Grounding, strict validation, and API reads. A top-10 pack exceeded the local 4096-token context and failed closed before the successful top-3 run.

## Runtime evidence

- Model download: 132.03 s; cache about 5.6 GiB.
- Cold loads observed: 3.43 s and 1.12 s after dependency correction.
- Basic completion: 2.636 s, 18.31 output tok/s, peak 6.147 GB.
- Strict JSON completion: 3.167 s, 16.89 output tok/s, peak 6.162 GB.
- Dev/Test task latency is recorded in each result JSON.
- `mlx-vlm /v1/models` lists all cached models; fixed model ID is mandatory.
- Final warm qualification: basic 0.707 s, strict structured 1.438 s, reasoning leakage false.

## Next actions

1. Add controlled fault-injection fixtures for actual timeout recovery and malformed structured output without weakening strict validation.
2. Requalify the same pipeline on Qwen3.8-27B AWQ INT4 + RTX 4090 + vLLM.
3. Keep RAW as default and treat Local Query Builder as experimental only.
4. Start Sprint 5A policy engine and human-review gate without turning LLM output into a final decision.

## Final validation ledger

- Ruff: PASS; Format: 275 files formatted/verified; Pyright: 0 errors/warnings.
- Default regression: 437 passed, 53 deselected.
- Architecture + Unit + Contract + E2E: 437 passed, 2 deselected.
- Integration: 42 passed, 5 external-GPU skipped, 443 deselected.
- External Local MLX: 3 passed, 487 deselected, skip 0.
- Migration: upgrade head and Alembic drift check PASS (`No new upgrade operations detected`).
- Runtime: Docker rebuild PASS; Core 6 healthy; four application queues consumer 1/depth 0.
- Persistence audit: 12 MLX analysis stages at prompt `2.0.0-local.2`, 10 MLX grounded results at
  prompt `1.1.0-local.2`; raw-prompt/raw-response/reasoning columns 0.
- `git diff --check`: PASS.

## Production target

Target remains Qwen3.8-27B AWQ INT4 on RTX 4090/vLLM. Existing qualification remains `QUALIFIED_WITH_LIMITATIONS`; it was unavailable for this run and requires separate target-model requalification. Local MLX metrics must not be presented as production performance.
