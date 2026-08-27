# Case Resolution State Machine

- Status: Accepted Sprint 5C design
- Date: 2026-08-27
- Implementation status: Implemented; current verification is linked from
  `docs/progress/SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`.

## Projection states

| State | Meaning | Terminal for normal Sprint 5C processing |
|---|---|---:|
| `DECISION_RECORDED` | Exact immutable Human Decision accepted for mapping | No |
| `ACTION_NOT_REQUIRED` | Mapping explicitly requires no external action | Yes |
| `MANUAL_FOLLOW_UP_REQUIRED` | Information or conflicting Decision requires a person | Yes |
| `ACTION_NEEDS_INPUT` | Required explicit action input is missing or invalid | Yes |
| `ACTION_READY` | Complete immutable Action Intent was created | No |
| `ACTION_DRY_RUN_PENDING` | Durable simulation request was stored | No |
| `ACTION_DRY_RUN_VALIDATED` | Network-free simulation validated the Intent | Yes |
| `ACTION_DRY_RUN_FAILED` | Network-free simulation rejected or failed the Intent | Yes |

“Terminal” means Sprint 5C provides no normal continuation command. A later version may add a new
append-only workflow, but must not mutate existing Decisions, Events, Intents, Attempts, or Results.

## Normal transitions

| From | Condition or event | To | Atomic durable records |
|---|---|---|---|
| No projection | Authenticated Human resolve commits | `DECISION_RECORDED` | Decision, Projection, decision-recorded Event, and durable request Event |
| `DECISION_RECORDED` | `REJECT_REQUEST` or `NO_ACTION` | `ACTION_NOT_REQUIRED` | Mapping Event only |
| `DECISION_RECORDED` | `PROVIDE_INFORMATION` | `MANUAL_FOLLOW_UP_REQUIRED` | Mapping Event only |
| `DECISION_RECORDED` | Approval with missing or invalid explicit input | `ACTION_NEEDS_INPUT` | Validation Event; Intent/Attempt/Result count remains zero |
| `DECISION_RECORDED` | Approval with complete explicit input | `ACTION_READY` | Immutable Action Intent and ready Event |
| `ACTION_READY` | Simulation consumer acquires a fenced execution lease | `ACTION_DRY_RUN_PENDING` | New `RUNNING` Attempt and pending Event; the outbox already exists |
| `ACTION_DRY_RUN_PENDING` | Deterministic simulation validates | `ACTION_DRY_RUN_VALIDATED` | Existing Attempt completion, immutable Result, validated Event, event consumption |
| `ACTION_DRY_RUN_PENDING` | Deterministic simulation fails closed | `ACTION_DRY_RUN_FAILED` | Existing Attempt completion, immutable Result or durable worker failure, failed Event |

`ACTION_READY` is committed with the simulation outbox. `ACTION_DRY_RUN_PENDING` is recorded only
when a consumer later acquires a simulation execution lease, so worker loss and lease recovery stay
observable without pretending the adapter has already run.

## Duplicate and conflict handling

An exact redelivery has the same durable event ID, Decision ID, Decision hash, Tenant, and Case. It
is a no-op and creates no second projection, Event, Intent, Attempt, or Result.

A request that references a different immutable Human Decision ID for the same Case is a conflict,
even if its decision type happens to match the first Decision. The existing Decision and any
existing Intent, Attempt, and Result remain unchanged. The projection transitions from its current
state to `MANUAL_FOLLOW_UP_REQUIRED`, a conflict Event records both Decision IDs, and no new Action
Intent is created.

This conflict transition is allowed from any current state. Re-delivery of the same conflict is a
no-op. Sprint 5C provides no automatic winner selection, supersession, amendment, or rollback.

## Concurrency and fencing

Every projection transition runs under a row lock and increments a unique, monotonic version/Event
sequence. Simulation completion additionally requires the exact active execution token. Concurrent
delivery therefore produces one committed transition, and a stale worker cannot commit after a
newer lease is acquired.

The following conditions fail closed before mutation:

- tenant, Case, Review Task, Decision, Resolution, or Intent identity mismatch;
- Human Decision or Action Intent content-hash mismatch;
- unknown Decision type, mapping version, Action type, mode, or event version;
- attempt to create a second Intent or terminal Result; and
- `LIVE` mode.

Infrastructure failure and outbox retry state remain delivery concerns; they do not invent a new
business transition or modify `cases.status`.

## No completion or closure path

`ACTION_NEEDS_INPUT` has no completion API in Sprint 5C. A user cannot patch Case attributes through
Resolution, resume the projection, or create an Intent manually. Likewise, neither
`ACTION_DRY_RUN_VALIDATED` nor any other Resolution state closes the Case.

## Related accepted decisions

- [ADR-0089](../../CSight_project_docs/docs/adr/0089-separate-case-resolution-lifecycle.md)
- [ADR-0092](../../CSight_project_docs/docs/adr/0092-atomic-resolution-request-and-immutable-intent.md)
- [ADR-0095](../../CSight_project_docs/docs/adr/0095-conflicting-human-decisions-require-follow-up.md)
