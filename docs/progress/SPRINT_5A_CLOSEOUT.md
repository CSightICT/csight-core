# Sprint 5A Independent Closeout

## Verdict

`POLICY_ENGINE_CORE_QUALIFIED_WITH_LIMITATIONS`

- P0 unresolved: 0
- P1 unresolved: 0
- Commit message: `feat: add versioned policy engine core`
- Push / pull request: none
- User-owned `kaputt_best_vision_architecture.md`: excluded from staging and unchanged

## Independent audit

- Immutable identity is `(tenant, rule_set_name, rule_set_version)` and a changed content hash is
  rejected. No rule update/delete repository is exposed.
- Activation history and evaluation results are append-only. Active selection is tenant- and
  `as_of_date`-scoped and rejects future or retired versions.
- Fields and operators come only from typed registries. Missing values remain explicit and the
  engine contains no expression, `eval`, `exec`, raw SQL, or arbitrary JSONPath execution.
- Mock Vision input produces `NOT_EVALUATED`; Local MLX action and ambiguity are not hard policy
  inputs. LLM issue/claim rules require human review and prohibit final decisions.
- Every one of 24 rules has a same-tenant, version/hash/effective-valid source clause. Retrieval and
  grounded prose cannot create runtime rules.
- Evaluation input is frozen at creation, queue payloads contain identifiers only, duplicate worker
  delivery is a no-op, and tenant-crossing reads return 404.

## Artifact and database evidence

| Item | Result |
|---|---|
| Tenants / rule sets / rules / source links | 2 / 2 / 24 / 24 |
| Rule artifact hash | `d1779452c5a9ec166a1a2e15a7cc61d4800d50a6be5a0161ea7d0f623889a918` |
| Re-ingestion | 0 inserted, 2 immutable sets validated |
| DB integrity | active 2; missing/orphan/mismatch/final effects 0 |
| Dev 80 | all correctness/replay metrics 1.0; forbidden/cross-tenant/future 0 |
| Sealed Test 40 | verifier PASS without re-executing the Test split |

## Verification ledger

| Gate | Actual result |
|---|---|
| Ruff / Format / Pyright | PASS / 296 files / 0 errors and warnings |
| Default regression | 456 passed, 55 deselected, 31 warnings |
| Isolated integration | 44 passed, 5 external-GPU skipped, 462 deselected, 3 warnings |
| Migration | Empty→0010, 0009→0010, 0010→0009→0010; drift 0 |
| Temporary databases | 0 remaining |
| Docker | API, Worker, Dispatcher, PostgreSQL, RabbitMQ, MinIO all healthy |
| Live policy smoke | 12 rules, replay 200, duplicate NOOP, tenant 404 |
| Qualification safety | Vision NOT_EVALUATED, missing image evidence, high-value manager review |
| Queue | five application queues, each consumer 1 and depth 0 |
| Git whitespace | `git diff --check` PASS |

The first round-trip command used the nonexistent descriptive revision
`20260827_0009_citation_grounding` and was rejected before migration. It was corrected to the actual
revision `20260827_0009`; previous-head and downgrade/upgrade paths then passed with zero drift.

## Limitations

- Rules and evaluations are synthetic implementation-correctness evidence, not validated company
  policy or legal guidance.
- Real Vision is unavailable and Local MLX remains `LOCAL_POC`.
- Human review, external refund/exchange execution, routing, final report, correction workflow, and
  policy editing remain outside Sprint 5A.

## Next action

Create the local closeout commit only, branch from it to
`feature/sprint-5b-human-review-workflow`, and keep final decisions human-only.
