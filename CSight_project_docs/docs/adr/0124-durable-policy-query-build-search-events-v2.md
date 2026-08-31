# ADR-0124: Durable Policy Query Build and Search Events v2

- Status: Accepted
- Date: 2026-08-31

## Context

ADR-0123 separated the model, retrieval, and decision worker queues, but Policy Query Build and
Policy Search still executed inside the legacy `policy_retrieval.requested.v1` task. A slow model
therefore occupied the same durable execution boundary as retrieval, and a process loss between
query generation and search could not resume from a persisted query plan.

## Decision

1. New policy-retrieval runs create `policy_query_build.requested.v2`. The payload contains only
   `event_id`, `tenant_id`, `case_id`, `retrieval_run_id`, and `correlation_id`.
2. Query Build claims the run, validates any pinned LLM route before a provider call, and stores the
   query plan. RAW and DETERMINISTIC strategies do not call a model provider.
3. Query-plan persistence, transition to `SEARCH_QUEUED`, consumption of the Query Build event, and
   creation of `policy_search.requested.v2` occur in one database transaction.
4. Search claims only `SEARCH_QUEUED` runs, reads the durable plan, executes the fixed HYBRID
   retrieval profile, stores hits and similarity diagnostics, and then terminalizes the run.
5. Model workers consume Query Build with concurrency 1. Retrieval workers consume Search with
   concurrency 2. The legacy v1 task remains registered only to drain already-published events;
   new runs do not emit v1.
6. Query Build and Search each have their own append-only outbox event for the same run. Event type
   and execution claim fencing reject delivery to the wrong worker, and bounded retry or poison
   handling ends in a durable failure without silently changing models.
7. Schema rollback is not part of application rollback after v2 events exist. A code rollback keeps
   the additive 0036 schema; database downgrade is only safe before any v2 Search event is created.

## Consequences

- A model timeout cannot consume retrieval-worker capacity, and Search can resume from the stored
  plan without regenerating queries.
- The default `RAW -> HYBRID -> Top 3` path invokes no LLM while using the same durable two-stage
  workflow.
- Query and Search events are independently observable and recoverable without putting customer
  content, policy text, credentials, or model output on RabbitMQ.
- Existing v1 records remain readable and drainable; no historical event or run is rewritten.
- Model and policy results remain advisory. Only an authenticated human records a final decision,
  and this change adds no refund, email, payment, shipping, or CRM side effect.
