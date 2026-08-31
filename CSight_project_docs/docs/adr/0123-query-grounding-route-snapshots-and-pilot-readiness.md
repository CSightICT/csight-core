# ADR-0123: Query/Grounding Route Snapshots and Fresh Pilot Evidence

- Status: Accepted
- Date: 2026-08-31

## Context

Text extraction already pinned an immutable signed model route, but LLM query building and
grounded explanation could still reach the global provider configuration without a historical
route check. Onboarding readiness also described configuration only; it could not prove that the
25 limited-pilot operational gates were both successful and recent.

## Decision

1. Migration `0035` adds `execution_mode`, nullable `model_route_plan_id`, and nullable route
   enforcement contract version to policy retrieval and grounded explanation runs. Existing rows
   remain valid and are not guessed or backfilled with a route.
2. Idempotency replay is checked before resolving an active route. A new LLM run snapshots its
   route in the same transaction as its run and outbox. RAW and DETERMINISTIC query strategies do
   not resolve a route and do not call an LLM.
3. Before a provider call, each model Worker validates the pinned historical task, execution mode,
   signed activation, deployment, model revision, prompt, schemas, runtime image, dependency lock,
   and SBOM identity. Automatic cross-model fallback remains prohibited.
4. Optional `LLM_TASK_RUNTIMES` settings separate endpoint, model identity, deployment, timeout,
   and circuit-breaker values by Extraction, Query Builder, and Grounding task.
5. `GET /api/v1/operations/pilot-readiness` joins the six onboarding configuration gates with the
   existing 25 operational qualification gates. Operational evidence is content-digested and
   expires after a configured interval; missing or stale evidence fails closed. Responses never
   contain tenant, Case, user, source content, Secret, or filesystem paths.
6. Models and policy output remain advisory. Only an authenticated human may record the final
   decision, and no refund, email, payment, shipping, or CRM side effect is introduced.

## Consequences

- Enforced Query Builder and Grounding runs cannot execute without their exact historical route.
- The default `RAW -> HYBRID -> Top 3` path remains available without an LLM route.
- The pilot cannot be reported ready from configuration alone or from expired evidence.
- Query generation and search have distinct queue names, but the current retrieval use case still
  executes both phases in one task. A v2 internal event boundary is still required before claiming
  independent model/search concurrency qualification.

The final consequence above was superseded by ADR-0124, which introduced durable Query Build and
Search v2 events while retaining v1 drain compatibility.
