# Sprint 5A — Versioned Deterministic Policy Engine Core

## Outcome

Sprint 5A implements a separate structured Policy Engine. It executes immutable typed rules and
never executes retrieval hits or generated language. Effects and summaries guide review but cannot
approve, reject, assign fraud, or assign liability.

## Implemented checklist

- [x] Field/operator registries and strict type compatibility, version `1.0.0`
- [x] Five condition statuses, four rule statuses, and versioned aggregation
- [x] Six non-final effect types; final-decision effects unrepresentable
- [x] Local LLM advisory restrictions and Mock Vision `NOT_EVALUATED`
- [x] Two synthetic tenant rule sets, 24 rules, 24 source-clause links
- [x] Immutable ingestion, append-only activation history, source tenant/version/hash validation
- [x] Migration `20260827_0010_policy_engine`, ten tables including outbox/effects
- [x] Input snapshot and qualification metadata without duplicated customer text
- [x] POST/List/Get API, identifier-only outbox, RabbitMQ route, thin Celery task
- [x] Append-only results and duplicate task `NOOP`
- [x] Dev 80 freeze and sealed Test 40 one-time evaluation
- [x] Twelve Accepted ADRs and policy architecture/schema/semantics/evaluation guides
- [x] Final full regression, migration lifecycle, rebuilt Docker live smoke

## Frozen evaluation

| Metric | Dev | Test |
|---|---:|---:|
| Rule-set selection | 1.000 | 1.000 |
| Rule exact match | 1.000 | 1.000 |
| Condition status | 1.000 | 1.000 |
| Effect F1 | 1.000 | 1.000 |
| Summary status | 1.000 | 1.000 |
| Source validity | 1.000 | 1.000 |
| Version accuracy | 1.000 | 1.000 |
| Deterministic replay | 1.000 | 1.000 |
| Forbidden final decisions | 0 | 0 |

These are synthetic implementation-correctness metrics, not production policy validation.

## Unresolved and next action

- Real Vision remains unavailable; Vision-dependent conditions stay `NOT_EVALUATED`.
- Local MLX remains `LOCAL_POC`; low-quality extracted action/ambiguity are not hard inputs.
- Evidence Alignment, final decisions, routing, review UI, override, final report, rule editor, and
  LLM rule generation remain out of scope.
- Next action: review the uncommitted Sprint 5A diff, then create a local closeout commit only when
  explicitly approved. Sprint 5B may connect these advisory effects to append-only human review.

## Verification ledger

| Gate | Actual result |
|---|---|
| Static | Ruff PASS; Ruff Format 296 files; Pyright 0 errors/warnings |
| Default regression | 456 passed, 55 deselected, 31 warnings |
| Target suites | Architecture 9; Unit 356; Contract 85 passed/2 skipped; E2E 6; Policy API/core 19 |
| Core integration | 44 passed, 5 external-GPU skipped, 462 deselected, 3 warnings |
| Migration unit/lifecycle | Empty→0010, 0009→0010, 0010→0009→0010; every path drift 0 |
| Live database | Head `20260827_0010_policy_engine`; Alembic drift 0 |
| Rule persistence audit | 2 active sets, 2 sets, 24 rules, 24 source links; integrity violations 0 |
| Frozen evaluation | Dev 80/Test 40; all exact/condition/effect/source/version/replay metrics 1.0 |
| Safety counters | Cross-tenant 0, future/retired 0, forbidden final decisions 0 |
| Docker runtime | API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6/6 healthy |
| Queue contract | `policy-evaluation` consumer 1, depth 0; five application queues consumed |
| Live async smoke | 12 rules, replay 200, duplicate `NOOP`, cross-tenant 404 |
| Qualification safety | Mock Vision `NOT_EVALUATED`; missing image requires evidence; high value requires manager review |

The first unisolated integration run had one outbox assertion failure because the long-running
Dispatcher claimed the test messages. With Worker/Dispatcher paused for test isolation, the complete
suite passed; both services were then restarted and returned healthy. A direct host Alembic command
also initially stopped before connecting because `.env` was not exported; the same command with the
configured environment confirmed head and zero drift.
