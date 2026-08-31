# ADR-0122: Task-specific model routes are append-only and pinned when analysis starts

- Status: Accepted
- Date: 2026-08-31

## Context

One tenant may qualify different signed language-model releases for text extraction, policy-query
construction, and grounded policy explanation. A single mutable active-model pointer cannot show
which release and deployment an existing analysis actually used. Reading the current pointer again
inside a Worker also makes an in-flight run change meaning when an administrator activates a newer
release.

ADR-0113 required the Worker to check the currently active signed release before each v2 provider
call. That protected the original extraction-only path, but it does not provide stable execution
identity once task-specific routes and administrative activation changes exist.

## Decision

- Signed LLM packages and activation chains are scoped by tenant, task, and execution mode. The
  initial task set is `PRODUCT_DEFECT_TEXT_EXTRACTION_V2`, `POLICY_QUERY_BUILDER_V1`, and
  `GROUNDED_POLICY_EXPLANATION_V1`.
- A model route plan is an immutable, tenant/task/mode-scoped link to one signed activation and one
  deployment identity. Activation uses compare-and-swap, a request hash, and a tenant/task/mode
  idempotency key. Rollback is another route-plan event; existing plans are never updated.
- Automatic cross-model fallback is always `false`. A timeout, unavailable deployment, signature
  failure, identity mismatch, or missing pinned record fails closed. A different model must be
  qualified, signed, activated, and routed explicitly.
- When route enforcement is configured, a new text-extraction v2 request resolves the active route
  only after its idempotency claim is known to be new. It snapshots the route-plan ID on the
  analysis stage in the same transaction as the run, stage, and outbox event. An idempotent replay
  returns the original run before route resolution, even when the current route later changes or
  disappears.
- A Worker validates the stage's pinned route-plan ID, the historical activation referenced by that
  plan, the signed release manifest, task, execution mode, route deployment ID, and its exact runtime
  identity (served model, artifact/runtime/dependency/SBOM digests, prompt, and input/output schema).
  It does not consult the current route or current activation. A later administrative activation
  therefore affects only new runs.
- `analysis_stage_runs.model_route_plan_id` is nullable for pre-ADR records and for configurations
  where route enforcement is disabled. No historical route is inferred or backfilled. A future
  backfill may populate only records with independently provable route and activation identity; it
  must remain additive and auditable.
- This decision supersedes ADR-0113 only for the v2 per-call lookup of the current active release.
  Its signed-manifest, exact runtime identity, qualification, and no-provider-call-on-failure gates
  remain in force and are now evaluated through the pinned route.
- `SHADOW` and `PRIMARY` retain separate activation and route chains. `SHADOW` output remains
  advisory and cannot create policy decisions, human-review decisions, resolutions, or external
  actions. In every mode, models only analyze evidence; an authenticated human remains the sole
  owner of final customer-service decisions.

## Consequences

- Every enforced v2 stage has a stable, reproducible route reference even if administrators change
  the active release while it is queued or running.
- Legacy stages remain readable and executable through the existing compatibility path while route
  enforcement is disabled. Enabling enforcement makes a missing pinned route a terminal,
  non-retryable failure before any provider call.
- Task-specific package versions may share a package name and version without colliding, while
  tenant and task foreign keys prevent cross-tenant or cross-task route substitution.
- Runtime composition and deployment settings must explicitly provide both the start resolver and
  pinned execution guard before enforcement can be claimed. Their wiring is a separate change.

## Related decisions

- [ADR-0103](0103-limited-pilot-execution-isolation-and-shadow-mode.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0113](0113-rtx4090-qwen-candidate-release-gate.md)
- [ADR-0121](0121-fail-closed-separated-pilot-runtime-profile.md)
