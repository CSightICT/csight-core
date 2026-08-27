# Case Resolution Architecture

- Status: Accepted Sprint 5C design
- Date: 2026-08-27
- Implementation status: Implemented in Sprint 5C; verification evidence is recorded in
  `docs/progress/SPRINT_5C_CASE_RESOLUTION_CONSOLE.md` and `docs/progress/CURRENT_STATUS.md`.

## Responsibility boundary

Case Resolution records what must happen after an immutable Human Decision. It is a separate
workflow from Case intake, Analysis, Policy Evaluation, and Human Review.

```text
authenticated resolve transaction
  -> case_resolution.requested.v1 durable outbox
  -> resolution worker
  -> immutable Action Intent, when inputs are complete
  -> external_action.simulation_requested.v1 durable outbox
  -> deterministic network-free DRY_RUN worker
```

The Human Decision remains the only final-decision source. Resolution maps that decision into a
typed assessment outcome and tracks post-decision processing. It never changes the decision and
never treats an LLM, Vision result, grounded explanation, policy effect, or reviewer rationale as an
executable parameter source.

## Lifecycle ownership

| Concern | Source of truth | Sprint 5C rule |
|---|---|---|
| Case intake status | `cases.status` | Unchanged by Resolution |
| Human final decision | Immutable Human Decision | Never updated or replaced |
| Resolution progress | One row-locked, versioned Resolution Projection per Case | Mutable only through serialized transitions |
| Resolution audit | Append-only Resolution Events | Never updated or deleted |
| Action command material | Immutable typed Action Intent | At most one for the accepted Case decision |
| Simulation execution | Append-only Attempt and Result | `DRY_RUN` only; no network side effects |
| Message delivery | Two distinct durable outboxes | At-least-once delivery with idempotent consumers |

No Resolution state implies Case closure. `ACTION_DRY_RUN_VALIDATED` means only that the immutable
intent passed the local simulation contract.

## Transaction boundaries

### Human resolve transaction

The authenticated resolve use case must store all of the following in one PostgreSQL transaction:

- Human Decision and validated basis rows;
- the existing Human Review `RESOLVED` action, assignment release, and task projection update; and
- one `case_resolution.requested.v1` outbox row tied to the exact Decision, Case, Review Task, and
  Tenant.

If any write fails, all writes roll back. The API must not return a successful resolve response with
a Decision that has no durable Resolution request.

### Resolution worker transaction

The worker consumes the exact event ID, reloads all referenced rows, and verifies tenant, Case,
Review Task, Decision identity, and Decision content hash before mapping. It then performs one of
these atomic outcomes:

- records `ACTION_NOT_REQUIRED` or `MANUAL_FOLLOW_UP_REQUIRED` and an append-only event;
- records `ACTION_NEEDS_INPUT` and an append-only event, without creating an Intent, Attempt, or
  Result; or
- creates one immutable Action Intent, records `ACTION_READY`, advances the projection, and stores
  one `external_action.simulation_requested.v1` outbox row.

The consumer marks the exact request event `CONSUMED` only in the same transaction as the durable
outcome. Permanent or retry-exhausted failure is stored with a bounded failure code.

### Simulation worker transactions

The simulation worker reloads and re-hashes the exact Action Intent before use. Its claim
transaction creates a `RUNNING` Attempt, stores the fenced execution token and lease, and records
`ACTION_DRY_RUN_PENDING`. The pure, network-free adapter then runs outside the transaction. A
separate completion transaction verifies the token, completes the Attempt, creates the immutable
Result and terminal Event, advances the projection, and consumes the exact simulation event. A crash
may repeat the pure calculation after lease expiry, but a stale token cannot commit a second Result.

## Persistence invariants

The Sprint 5C schema must enforce, rather than merely assume, these identities:

- one Resolution Projection per `(tenant_id, case_id)`;
- monotonically versioned Resolution Events per Resolution;
- one Action Intent per `(tenant_id, resolution_id)` and per accepted Human Decision;
- tenant-and-Case composite foreign keys between Decision, Resolution, Intent, Outbox, Attempt, and
  Result rows;
- at most one terminal Result per Intent and per simulation Attempt;
- verified Human Decision, Action Intent, and Simulation Result content hashes; append-only Events
  and Attempts; and
- `side_effects_performed = false` for every Sprint 5C simulation Result.

The projection and an Attempt's fenced lifecycle fields are the only mutable workflow records.
Projection row locks, monotonically increasing versions, unique Event sequences, and execution
tokens serialize transitions. Replayed events with the same event ID and immutable identity are
no-ops. A different Decision ID for the same Case is not a replay; it follows the conflict rule in
[`CASE_RESOLUTION_STATE_MACHINE.md`](CASE_RESOLUTION_STATE_MACHINE.md).

## Durable event boundaries

Sprint 5C uses distinct durable outboxes so Resolution mapping and Action Simulation cannot be
mistaken for one execution step.

| Event | Producer transaction | Consumer | Identifier-only queue payload |
|---|---|---|---|
| `case_resolution.requested.v1` | Authenticated Human resolve | Resolution worker | event, tenant, Case, Resolution, correlation IDs |
| `external_action.simulation_requested.v1` | Complete Intent creation | Simulation worker | event, tenant, Case, Intent, correlation IDs |

Each outbox has a claim token, lease, publish-attempt count, bounded backoff, and
`PENDING/PROCESSING/PUBLISHED/FAILED/CONSUMED` lifecycle. Broker confirmation can be followed by a
publisher crash, so duplicate delivery is expected. Consumers validate the exact event row and rely
on database uniqueness and fenced writes rather than exactly-once delivery.

Queue payloads contain identifiers only. They exclude customer text, reviewer rationale, policy
text, Action parameters, addresses, JWTs, credentials, and signed URLs.

## Read-only public API

Sprint 5C adds only authenticated reads:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/cases/{case_id}/resolution` | Current CAS projection and immutable Decision reference |
| `GET` | `/api/v1/cases/{case_id}/resolution/events` | Ordered append-only Resolution Events |
| `GET` | `/api/v1/cases/{case_id}/external-action-intents` | Case-scoped immutable Intent summaries |
| `GET` | `/api/v1/external-action-intents/{intent_id}` | Intent, Attempts, and Results |

`ADMIN`, `REVIEWER`, and `QUALITY_VIEWER` may read these projections. Tenant is always derived from
the authenticated Principal. Cross-tenant item/projection reads are hidden with `404`; collection
reads return no rows and disclose no foreign identity. Read projections exclude claim tokens,
leases, internal dispatcher metadata, queue payloads, and credentials. Sprint 5C adds no public
Resolution mutation or external-execution endpoint.

## Explicit exclusions

Sprint 5C does not implement:

- Case closure or any `cases.status` transition;
- Review-stage or Resolution-stage input completion;
- Human Decision amendment, correction, deletion, or replacement;
- `LIVE` external execution;
- payment, refund, exchange, reshipment, repair, CRM, notification, or customer-message calls;
- automatic assignment, SLA routing, OIDC, or row-level security; or
- a server-side workflow coordinator.

The client may compose existing idempotent APIs and resume by opaque run identifiers, but it does
not gain authority to bypass these boundaries.

## Related accepted decisions

- [ADR-0089](../../CSight_project_docs/docs/adr/0089-separate-case-resolution-lifecycle.md)
- [ADR-0090](../../CSight_project_docs/docs/adr/0090-versioned-human-decision-action-mapping.md)
- [ADR-0091](../../CSight_project_docs/docs/adr/0091-explicit-external-action-inputs-only.md)
- [ADR-0092](../../CSight_project_docs/docs/adr/0092-atomic-resolution-request-and-immutable-intent.md)
- [ADR-0093](../../CSight_project_docs/docs/adr/0093-durable-resolution-and-simulation-outboxes.md)
- [ADR-0094](../../CSight_project_docs/docs/adr/0094-dry-run-only-external-action.md)
- [ADR-0095](../../CSight_project_docs/docs/adr/0095-conflicting-human-decisions-require-follow-up.md)
