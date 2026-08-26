# Sprint 4C-3A — Citation Pack and Grounding Guardrails

## Outcome

Implementation is complete on `feature/sprint-4c3a-citation-grounding-guards`. Successful policy
retrieval runs can create a content-hashed immutable Citation Pack and an asynchronous grounded
explanation run. The stored output is strict, decision-free, citation-allowlisted, and append-only.

Deterministic evaluation over synthetic Grounding 50 and Prompt Injection 30 produced zero
structural violations and 100% deterministic replay. This qualifies structure and orchestration,
not semantic model quality. Semantic metrics remain `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`.

## Handoff checklist

- [x] Sprint 4C-2 closeout commit `a282817`; Push·PR 없음
- [x] Dedicated `feature/sprint-4c3a-citation-grounding-guards` branch
- [x] Immutable content-hashed Citation Pack with clause/version/retrieval snapshots
- [x] Strict grounded output schema with fixed neutral summary and cited statements
- [x] Citation allowlist, tenant/version/effective-date, duplicate, and forbidden-field guardrails
- [x] Append-only run/result/profile/outbox migration `20260827_0009`
- [x] Identifier-only RabbitMQ/Celery route and thin Worker entrypoint
- [x] POST/List/Get API with tenant scoping and Viewer read-only behavior
- [x] Mock generation E2E contract and vLLM strict-schema adapter contract
- [x] Grounding 50 + Injection 30 structural qualification artifacts
- [x] Semantic metrics explicitly skipped rather than inferred from Mock output
- [ ] Real Qwen Grounding Dev qualification, prompt freeze, and sealed Test when available
- [ ] Sprint 4C-3B semantic faithfulness and unsupported-claim qualification
- [ ] Sprint 5 versioned Policy Engine and Human Review integration

## Actual verification — 2026-08-27

- Ruff PASS; format PASS; Pyright 0 errors/warnings
- Fast regression PASS: 431 passed, 3 external skipped, 47 deselected, 31 warnings
- Core Integration PASS: 42 passed, 5 external GPU skipped, 434 deselected
- Target grounding unit/contract/migration PASS: 12 passed
- Structural evaluation PASS: Grounding 50, Injection 30, structural violation 0, replay 100%
- Semantic metrics SKIPPED: external Qwen endpoint unavailable
- PostgreSQL Migration PASS: empty/previous/round-trip to `20260827_0009`, drift 0, temporary
  databases removed; current development database is `20260827_0009 (head)`
- Live Mock orchestration PASS: PostgreSQL + RabbitMQ + Celery produced 10 citations and 10
  grounded statements, replay 200, cross-tenant detail 404, and no internal clause row ID exposure
- Provider-down PASS: vLLM connection failure ended as
  `GROUNDED_EXPLANATION_PROVIDER_UNAVAILABLE` with no result and no Mock fallback
- Verification cleanup PASS: targeted Grounding smoke/down runs 3, results 2, outbox events 3,
  Citation Pack items 10, and orphan Pack 1 removed; target runs remaining 0
- Docker rebuild PASS after one bounded retry: the latest image built with Dockerfile diff 0; all
  six Core services are healthy and live/ready return 200
- Compose/runtime queue PASS: the current Worker consumes
  `default,analysis,policy-retrieval,grounded-explanation`; all four queues are empty with one
  consumer each
- Docker Grounding E2E PASS: 10 citations/statements, replay 200, cross-tenant detail 404, and two
  duplicate terminal deliveries left one run and one result
- Docker provider-down PASS: a vLLM connection failure terminated as
  `GROUNDED_EXPLANATION_PROVIDER_UNAVAILABLE` with result 0 and Mock fallback 0; the default Worker
  was restored and all services remained healthy

## Next action

Create the user-authorized local closeout commit `feat: add citation grounding guardrails`, without
Push or PR. From that clean baseline, create `feature/sprint-4c3b-local-mlx-grounding` and qualify
the preferred pinned Local MLX artifact on Dev only before any sealed Test access. Do not treat the
successful Docker/Mock structural runtime as semantic-model qualification.
