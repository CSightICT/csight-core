# Sprint 4C-2 — Policy Query Builder

## Outcome

Implementation is complete on `feature/sprint-4c2-policy-query-builder` and fixed in the local
closeout commit `feat: add case-based policy retrieval query planning`; no Push or PR was created.
The external Qwen endpoint was unavailable, so Qwen Extraction v2 and real LLM Query Builder
qualification are explicitly skipped. The new sealed dataset contains Dev 80/Test 40 with stable
hash `5040f219aff5546a88073f132889215df2574c3196bdcad9f4f9e28141fd72c4`.

Dev RAW MRR@10 was 0.709549 versus deterministic 0.667133; both Recall@10 were 1.0. Test was run once
after the RAW profile freeze: RAW Recall@10/MRR@10/nDCG@10 were 0.975/0.739236/0.741392 and
deterministic were 1.0/0.724544/0.657571. RAW is selected among evaluated strategies, but the Sprint
decision is `BLOCKED_EXTERNAL_LLM` because real LLM performance is unknown.

## Handoff checklist

- [x] 4C-1 closeout commit `14cae29` and 4C-2 branch
- [x] External Qwen availability checked; explicit skip recorded
- [x] New Dev 80/Test 40 holdout generated, validated, and sealed
- [x] Strict Query Plan, deterministic builder, LLM provider method, and prompt 1.1.0
- [x] Frozen HYBRID per-query retrieval and versioned multi-query RRF provenance
- [x] Append-only Run/Query/Hit/Profile/Outbox migration and repositories
- [x] POST/List/Get API, idempotency, tenant scope, Viewer read-only
- [x] Identifier-only queue, thin Worker, no silent fallback
- [x] RAW and deterministic Gold-Extraction evaluation; Test used once
- [x] LLM/Model-Extraction metrics marked Skipped, not replaced with Mock
- [x] Deterministic and Mock-LLM live run success; provider/embedding-down failure checks
- [x] RAW remains the default; deterministic and LLM remain explicit experiment strategies
- [x] Local closeout commit created without Push or PR
- [ ] Real Qwen Extraction v2 Dev/freeze/Test when an approved endpoint is available
- [ ] Real LLM Query Builder Dev/freeze/Test when an approved endpoint is available
- [ ] Sprint 4C-3 citation pack and grounded explanation

## Next action

Start Sprint 4C-3A on a dedicated branch with immutable citation packs, a clause allowlist, strict
grounded-explanation schema, deterministic structural validators, Mock E2E, and offline grounding
evaluation. Keep semantic faithfulness metrics skipped until a pinned Qwen3.8 endpoint is available.

## Actual verification — 2026-08-27

- Ruff PASS; format PASS 252 files; Pyright 0 errors/warnings
- Fast regression 419 passed, 50 deselected, 31 warnings
- Unit 327 passed/17 warnings; Architecture 8 passed; Contract 78 passed/2 deselected/6 warnings
- E2E 6 passed/8 warnings; PostgreSQL Integration 42 passed/5 skipped/411 deselected/3 warnings
- External embedding 1 passed/468 deselected; external Qwen explicitly Skipped
- Migration empty, previous, and `0008→0007→0008` round-trip PASS; three DBs drift 0 and removed
- Docker API/dispatcher/worker/PostgreSQL/RabbitMQ/MinIO all healthy; Core readiness 200
- Real broker flow Case→v2→Run+Outbox→RabbitMQ→Worker→2 queries→10 hits→SUCCEEDED
- Provider-down and embedding-down produced FAILED without silent fallback; duplicate execution NOOP
- `git diff --check` PASS; Sprint 4C-2 fixed in a local closeout commit with no Push or PR
