# Human Decision Contract

## Creation

`POST /api/v1/human-review-tasks/{task_id}/resolve` is the only creation path. It requires an
authenticated Admin or Reviewer, a claimed task, current assignee or audited Admin override, CAS
version, a 10–2000 character human rationale, one or more reason codes, and validated basis.
Manager and safety tasks require Admin resolution.

## Decision types

`APPROVE_REFUND`, `APPROVE_EXCHANGE`, `APPROVE_RESHIPMENT`, `APPROVE_REPAIR`, `REJECT_REQUEST`,
`PROVIDE_INFORMATION`, and `NO_ACTION`. These values do not exist as Policy Engine effects.

## Basis

Allowed types are `POLICY_RULE_RESULT`, `POLICY_CITATION`, `CASE_EVIDENCE`, and `ANALYSIS_RESULT`.
Approval/rejection requires a packet-scoped policy rule result or citation. Unknown citations,
wrong-run rules/evidence, duplicate references, and cross-tenant resources fail closed.

## Derived outcome relation

The server deterministically records `CONSISTENT_WITH_RECOMMENDATION`,
`DIFFERS_FROM_RECOMMENDATION`, `NO_COMPARABLE_RECOMMENDATION`, or `INDETERMINATE_POLICY` under rule
version `1.0.0`. It is descriptive and does not mark the reviewer right or wrong.

## Immutability

One `(tenant_id, review_task_id)` decision is permitted. There is no update/delete API or repository
operation. The content hash covers the reviewer input, derived relation, actor, and schema version.
