# Human Review State Machine

| From | Action | To | Actor |
|---|---|---|---|
| `PENDING` | `CLAIMED` | `CLAIMED` | Admin; Reviewer for standard/evidence/exception |
| `CLAIMED` | `RELEASED` | `PENDING` | Assignee or Admin override |
| `CLAIMED` | `EVIDENCE_REQUESTED` | `WAITING_FOR_EVIDENCE` | Assignee or Admin override |
| `WAITING_FOR_EVIDENCE` | `RESUMED` | `CLAIMED` | Retained assignee with new evidence; Admin with reason |
| `CLAIMED` | `ESCALATED` | `ESCALATED` | Assignee or Admin override |
| `ESCALATED` | `CLAIMED` | `CLAIMED` | Admin only |
| `CLAIMED` | `RESOLVED` | `RESOLVED` | Assignee/Admin; manager and safety Admin only |

All other transitions fail with `INVALID_REVIEW_TRANSITION`. Each request supplies
`expected_version`; stale writes fail with `REVIEW_TASK_VERSION_CONFLICT`. A row lock and unique
action version ensure one concurrent claim wins.

Release requires a reason code or rationale. `OTHER` evidence and escalation reasons require a
rationale. Evidence requests preserve the assignee and the active assignment interval while the task
waits, so the inquiry remains in that person's active queue. Resume requires AVAILABLE evidence created
after the packet or an explicit Admin reason and returns directly to `CLAIMED`. Resolved is terminal in
Sprint 5B.
