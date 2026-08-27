# Human Review Architecture

## Responsibility boundary

`LLM/Vision → Retrieval/Grounding → Policy Engine → Review Request → Human Review` is a one-way
advisory flow. Policy evaluation emits `human_review.requested.v1`; a thin worker creates exactly
one task, immutable packet, and `CREATED` action. Only an authenticated API action creates a final
decision.

The platform core contains mapping, state, permission helpers, decision validation, and outcome
relation rules without FastAPI, SQLAlchemy, Celery, HTTPX, or provider SDK dependencies. Ports
describe persistence; adapters own SQLAlchemy and Celery details.

## Transaction boundaries

- Policy success and the review-request outbox row are committed together.
- Task, packet, and `CREATED` action are committed together.
- Claim/release/evidence/escalation actions, assignment history, and task projection are committed
  together.
- Decision, basis, `RESOLVED` action, assignment release, and task projection are committed
  together.

## Safety boundary

No path executes refunds, exchanges, reshipments, payment cancellation, CRM updates, customer
notifications, or reports. Grounded explanation is advisory. Qualification metadata is visible.
Raw prompts, raw model responses, reasoning, customer text, vectors, credentials, and secrets are
not copied into review audit records.

## Versioned contracts

| Contract | Version |
|---|---|
| Task mapping | `review_task_mapping/1.0.0` |
| Packet | `1.0.0` |
| Human decision | `1.0.0` |
| Outcome relation | `review_outcome_relation/1.0.0` |
| Queue event | `human_review.requested.v1` |

## Deferred

Frontend, automatic assignment, SLA escalation, notifications, external execution, final report,
decision amendment, and packet revision are explicitly outside Sprint 5B.
