# Sprint 4C-3B Closeout — Local MLX LLM Grounding PoC

## Verdict

`PASS`. The independent closeout audit found no unresolved P0 or P1 issue in the approved
Sprint 4C-3B scope. The pinned Local MLX runtime, provider boundary, frozen evaluation artifacts,
strict citation grounding, Core integration, migration, and Docker health gates all passed.

This verdict is limited to the Local PoC. Extraction action and ambiguity quality remain weak,
RAW remains the selected query strategy, and the small synthetic grounding set is not production
faithfulness evidence. Qwen3.8 on RTX 4090/vLLM remains a separate production target.

## Closeout checklist

- [x] P0 unresolved: 0
- [x] P1 unresolved: 0
- [x] Artifact `mlx-community/Qwen3.5-9B-MLX-4bit` and immutable revision audited
- [x] MLX 0.32.2 and mlx-vlm 0.6.17 runtime identity audited
- [x] `LOCAL_POC` and Qwen3.8 production-target metadata remain distinct
- [x] Mock and vLLM providers remain available behind the same port
- [x] Docker host bridge, Core DB isolation, and no-silent-fallback boundaries audited
- [x] Extraction, Query Builder, Grounding, and Injection artifacts verified without rerunning Test
- [x] Frozen prompt hashes match the current registered Local prompts
- [x] RAW query strategy and non-default reranker boundary preserved
- [x] Citation allowlist, required statement citations, duplicate normalization, and fail-closed behavior audited
- [x] Actual unreachable-provider call returned retryable provider `mlx`; Core readiness remained 200
- [x] PostgreSQL, RabbitMQ/Outbox, API/E2E, tenant-isolation, and duplicate-delivery regression passed
- [x] Migration upgrade and drift check passed at `20260827_0009`
- [x] Six Docker Core services healthy; application queues had one consumer and zero messages
- [x] Raw prompt, raw response, reasoning, and chain-of-thought persistence columns absent
- [x] Documentation and handoff status updated
- [x] `git diff --check` passed
- [x] `kaputt_best_vision_architecture.md` was not modified, staged, or committed
- [x] Local closeout commit authorized with message `feat: add local MLX LLM grounding PoC`
- [x] Push and PR prohibited

## Actual verification — 2026-08-27

| Gate | Result | Evidence |
|---|---|---|
| Ruff lint | PASS | 0 violations |
| Ruff format | PASS | 275 files unchanged |
| Pyright | PASS | 0 errors, 0 warnings |
| Default regression | PASS | 437 passed, 53 deselected |
| Architecture + Unit + Contract + API/E2E | PASS | included in the 437-test default suite |
| PostgreSQL integration | PASS | 42 passed, 5 external-GPU skipped, 443 deselected |
| External Local MLX | PASS | 3 passed, 487 deselected |
| Base runtime qualification | PASS | constrained JSON and basic completion; reasoning leakage false |
| Extraction artifact | PASS | Test40 schema/quote 100%; issue/action/ambiguity F1 0.8533/0.1935/0.1951 |
| Query artifact | PASS | Test40 Local Recall@10 0.90; RAW 0.975; `RAW_REMAINS_SELECTED` |
| Grounding artifact | PASS | Test10 and Injection Test10 structural/citation gates 100%; violations 0 |
| Frozen profiles | PASS | three frozen profiles; code prompt hashes match; Test rerun guard active |
| Provider down | PASS | actual unused endpoint returned retryable `LLMProviderUnavailableError`, provider `mlx` |
| Core readiness | PASS | PostgreSQL, RabbitMQ, and MinIO `ok`; optional MLX not a readiness dependency |
| Persistence audit | PASS | 12 MLX extraction stages, 10 MLX grounding results; duplicate result groups 0 |
| Raw payload retention | PASS | forbidden persistence columns 0 |
| Migration upgrade | PASS | current head `20260827_0009` |
| Migration drift | PASS | `No new upgrade operations detected` |
| Docker health | PASS | six Core services healthy |
| RabbitMQ | PASS | four application queues consumer 1, depth 0 |
| Local MLX restart smoke | NOT_RUN | running server had no ownership PID file; it was not stopped unsafely |
| Actual timeout-to-recovery | NOT_RUN | `OFFLINE_CONTRACT_ONLY` |
| Malformed-provider runtime injection | NOT_RUN | `OFFLINE_CONTRACT_ONLY` |
| `git diff --check` | PASS | no whitespace errors |

## Audited limitations

- Extraction requested-action F1 is 0.1935 and text-ambiguity F1 is 0.1951. These model-derived
  fields must not become hard Policy Engine eligibility inputs.
- Query Builder Test Recall@10 is 0.90 versus RAW 0.975. Local LLM query generation remains
  experimental and is not enabled as the default path.
- Local grounding passed the frozen synthetic Test10 and human spot-check scope only. It is not
  evidence of production policy faithfulness or legal correctness.
- The 4096-token Local runtime uses a top-3 Citation Pack for the safe-default E2E. The observed
  top-10 context overflow failed closed and is not hidden by truncation.
- Actual timeout-to-recovery and malformed-provider runtime fault injection remain
  `OFFLINE_CONTRACT_ONLY`; neither is reported as PASS.

## Handoff

Commit only the audited Sprint 4C-3B paths with the exact message
`feat: add local MLX LLM grounding PoC`, verify that the only remaining worktree item is the
unrelated Kaputt document, and create `feature/sprint-5a-policy-engine-core`. Sprint 5A changes must
remain uncommitted and must not be pushed or opened as a PR.
