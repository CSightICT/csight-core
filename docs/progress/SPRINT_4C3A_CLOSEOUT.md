# Sprint 4C-3A Closeout — Citation Grounding Guardrails

## Verdict

`PASS`. The independent closeout audit found no unresolved P0 or P1 issue in the approved
Sprint 4C-3A scope. Citation packs are immutable retrieval snapshots, generated citations are
restricted to a pack-local allowlist, grounded outputs are decision-free and append-only, and the
asynchronous runtime fails closed without a Mock fallback.

This verdict qualifies structural grounding and runtime behavior only. It does not qualify semantic
citation support, unsupported-claim rate, or paraphrase faithfulness; those remain pending an actual
model evaluation in Sprint 4C-3B.

## Closeout checklist

- [x] P0 unresolved: 0
- [x] P1 unresolved: 0
- [x] Citation Pack snapshot and append-only invariants audited
- [x] Pack-local citation allowlist and duplicate normalization audited
- [x] Cross-tenant, wrong-run, wrong-version, future/retired policy paths fail closed
- [x] Decision-free strict schema, required statement citations, and extra-field rejection audited
- [x] Run and outbox transaction, identifier-only message, and thin Worker entrypoint audited
- [x] Duplicate delivery leaves one run and one result; terminal replay is a no-op
- [x] Provider-down terminates with a stable error and creates no result or Mock fallback
- [x] Migration `20260827_0009` passes empty, previous, and downgrade/upgrade paths with drift 0
- [x] Latest Docker image consumes `grounded-explanation`; Core services and queues are healthy
- [x] Structural Grounding 50 + Injection 30 pass with deterministic replay
- [x] Documentation and handoff status updated
- [x] `kaputt_best_vision_architecture.md` was not modified, staged, or committed
- [x] Local closeout commit authorized with message `feat: add citation grounding guardrails`
- [x] Push and PR prohibited

## Independent audit findings

### Citation and persistence boundary

- A successful retrieval run is copied into a content-hashed Citation Pack containing tenant,
  rank, clause/document identifiers and versions, title/section/type/text, effective interval,
  source metadata, matched query identifiers, query strategy, and retrieval profile hash.
- Grounding validates only pack-local stable citation identifiers. Unknown citations fail closed;
  duplicates are normalized deterministically.
- Composite persistence constraints and application checks prevent cross-tenant, wrong-run, and
  wrong-version mixing. A pack is not rebuilt from later policy state.
- Grounding run, result, pack, items, profile, and outbox records preserve the append-only contract.
  No raw prompt, raw provider response, or chain-of-thought/reasoning field is stored.

### Output and runtime boundary

- Every policy statement requires at least one allowlisted citation. The schema rejects extra
  fields and contains no approval, rejection, fraud, responsibility, liability, or final-decision
  ownership fields.
- A run and its outbox event are created in one transaction. RabbitMQ/Celery messages contain
  identifiers only, and the Worker delegates to the application use case.
- Re-delivering the same terminal event twice produced one run and one result. An unavailable vLLM
  provider ended as `GROUNDED_EXPLANATION_PROVIDER_UNAVAILABLE`, with zero result rows and no Mock
  fallback.

## Actual verification — 2026-08-27

| Gate | Result | Evidence |
|---|---|---|
| Ruff format | PASS | 258 files unchanged |
| Ruff lint | PASS | 0 violations |
| Pyright | PASS | 0 errors, 0 warnings |
| Fast regression | PASS | 431 passed, 3 skipped, 47 deselected, 31 warnings |
| Architecture + Unit + Contract + E2E | PASS | 431 passed, 2 skipped, 31 warnings |
| PostgreSQL integration | PASS | 42 passed, 5 external-GPU skipped, 434 deselected |
| Grounding target tests | PASS | 12 passed |
| Structural evaluation | PASS | Grounding 50 + Injection 30; violations 0; replay 100% |
| Semantic evaluation | SKIPPED | `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| Migration lifecycle | PASS | empty/previous/round-trip `0009`; drift 0; three temporary DBs removed |
| Docker rebuild | PASS | latest image built; Dockerfile diff 0; six Core services healthy |
| Live Mock orchestration | PASS | 10 citations/statements; replay 200; cross-tenant detail 404 |
| Duplicate delivery | PASS | run 1, result 1, queue depth 0 after two redeliveries |
| Provider down | PASS | stable unavailable error; result 0; Mock fallback 0 |
| Runtime cleanup | PASS | all targeted verification runs removed; target runs remaining 0 |

Registry metadata access initially stalled during one build attempt. The incident remains in the
append-only validation/session history, but the bounded retry subsequently built the latest image
and completed the Docker runtime gates. Current status is therefore:

```text
APPLICATION_QUALIFICATION=PASS
DOCKER_REBUILD=PASS
EXISTING_CORE_RUNTIME=HEALTHY
DOCKERFILE_DIFF=0
```

## Remaining limitations

- Semantic citation precision/recall, unsupported-policy-claim rate, and paraphrase faithfulness
  are not qualified by Mock or structural evaluation.
- The synthetic reference corpus is not evidence of legal correctness or real enterprise policy
  quality.
- Retry scheduling, stale-claim recovery, and profile-version evolution beyond the frozen 4C-3A
  profile remain follow-up design work; they do not invalidate the audited single-attempt contract.
- Policy Engine and Human Review continue to own decisions; Grounded Explanation does not.

## Handoff

Create the local closeout commit on `feature/sprint-4c3a-citation-grounding-guards`, verify the
worktree contains only the unrelated untracked Kaputt document, and then create
`feature/sprint-4c3b-local-mlx-grounding`. Sprint 4C-3B must remain uncommitted and must not be
pushed or opened as a PR.
