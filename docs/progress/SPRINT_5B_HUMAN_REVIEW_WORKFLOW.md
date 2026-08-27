# Sprint 5B — Human Review Workflow Implementation and Closeout Gate

## 1. Current verdict and Git handoff

`CLOSEOUT_PASS_WITH_PRODUCT_LIMITATIONS`

- P0 unresolved: 0
- P1 unresolved: 0
- Sprint 5A baseline: `67eafdd feat: add versioned policy engine core`
- Branch: `feature/sprint-5b-human-review-workflow`
- Sprint 5B Commit / Push / PR: none
- User-owned `kaputt_best_vision_architecture.md`: untouched and unstaged

The normal Task→Packet→Claim/Action→human Resolve path and the reliability Closeout are complete.
Durable outbox crash recovery/backoff, worker lease and late-result fencing, terminal consumer
failure persistence, Packet/Decision hash revalidation, isolated integration DB, and the complete
regression gate passed on the final diff.

## 2. Review task

| Item | Value |
|---|---|
| Mapping | `review_task_mapping/1.0.0` |
| Task types | Standard, Evidence, Manager, Policy Exception, Safety |
| Priorities | Low, Normal, High, Critical |
| Live task / packet / created action | 1 / 1 / 1 for the selected smoke run |
| Duplicate event | `NOOP`; counts remain 1 / 1 / 1 |
| Packet | Immutable, content-hashed, tenant/run scoped |

Review-producing policy effects are aggregated deterministically. The highest-precedence task is
created and every effect remains in the packet. Policy effects never become final decisions.

## 3. State machine

| From | Action | To | Role |
|---|---|---|---|
| PENDING | CLAIM | CLAIMED | Admin; Reviewer for standard/evidence/exception |
| CLAIMED | RELEASE | PENDING | Assignee or Admin override |
| CLAIMED | REQUEST_EVIDENCE | WAITING_FOR_EVIDENCE | Assignee or Admin override |
| WAITING_FOR_EVIDENCE | RESUME | PENDING | New evidence or Admin reason |
| CLAIMED | ESCALATE | ESCALATED | Assignee or Admin override |
| ESCALATED | CLAIM | CLAIMED | Admin |
| CLAIMED | RESOLVE | RESOLVED | Assignee/Admin; Manager/Safety Admin only |

Every accepted transition writes an append-only action and updates the CAS projection in one
transaction. Repository integration exercised release, evidence request, Admin resume, escalation,
four assignment cycles, resolve, and complete ordered action history.

## 4. Migration

Feature-schema revision: `20260827_0011_human_review`

| Table | Purpose |
|---|---|
| `human_review_tasks` | Versioned queue projection and current assignee |
| `human_review_packets` | One immutable review-time input snapshot |
| `human_review_actions` | Append-only state transition audit |
| `human_review_assignments` | Claim/release history and exclusive active assignment |
| `human_review_decisions` | One immutable human final-decision record per task |
| `human_review_decision_basis` | Tenant- and packet-scoped validated references |
| `human_review_request_events` | Durable bounded-retry review-request delivery |

Empty→0011, 0010→0011, and 0011→0010→0011 passed with drift 0. Two explicitly named temporary
databases were deleted and the remaining count was verified as zero.

Closeout adds the follow-on `20260827_0012_async_reliability` revision for durable claim metadata,
publish backoff and terminal consumer state. Empty→0012, 0011→0012, and 0012→0011→0012 passed
with drift 0; every disposable database was removed and the remaining count was verified as zero.

## 5. Authorization

| Action | ADMIN | REVIEWER | QUALITY_VIEWER |
|---|---|---|---|
| View queue/detail | Allowed | Allowed | Allowed |
| Claim Standard/Evidence/Exception | Allowed | Allowed | Forbidden |
| Claim Manager/Safety/Escalated | Allowed | Forbidden | Forbidden |
| Release/Evidence/Escalate | Allowed, override audited | Own claimed task | Forbidden |
| Resolve Standard | Allowed, override audited | Own claimed task | Forbidden |
| Resolve Manager/Safety | Allowed | Forbidden | Forbidden |

Tenant comes only from the authenticated principal. Cross-tenant list/detail/action references are
hidden or rejected. The live gate observed Viewer read 200/action 403, Reviewer Manager claim 403,
and cross-tenant detail 404.

## 6. Human decision

- Types: approve refund/exchange/reshipment/repair, reject, provide information, no action
- Rationale: reviewer-entered, trimmed, 10–2000 characters
- Basis: rule result, citation, case evidence, or analysis result; approval/rejection requires policy
  rule or citation basis
- Validation: packet citation allowlist, same policy run, frozen analysis evidence, same tenant
- Outcome relation: deterministic `review_outcome_relation/1.0.0`
- Immutability: unique `(tenant_id, review_task_id)`, content hash, no update/delete repository/API

Decision, basis, `RESOLVED` action, assignment release, and task projection share one transaction.
No worker, policy, LLM, Vision, RAG, or grounding path imports or calls resolve.

## 7. Workflow metrics

| Metric | Dev 60 | Sealed Test 30 |
|---|---:|---:|
| Task Mapping | 1.0 | 1.0 |
| Task Priority | 1.0 | 1.0 |
| State Transition | 1.0 | 1.0 |
| Authorization | 1.0 | 1.0 |
| Assignment | 1.0 | 1.0 |
| Decision Basis | 1.0 | 1.0 |
| Outcome Relation | 1.0 | 1.0 |
| Audit Completeness | 1.0 | 1.0 |
| Deterministic Replay | 1.0 | 1.0 |

Dev was frozen before Test. Test ran once; subsequent verification reads immutable artifacts and
checks their dataset/profile hashes.

## 8. Safety gates

| Gate | Result |
|---|---|
| Cross-tenant violation | 0 |
| Unauthorized final decision | 0 |
| Worker-created decision | 0 |
| Policy-created decision | 0 |
| Duplicate task / decision | 0 / 0 |
| Unknown citation basis | 0 |
| Wrong-run basis | 0 |
| Decision overwrite | 0 |
| Raw prompt/response/reasoning in API/audit | 0 observed paths |

Grounded explanation is returned with `advisory: true`. Qualification snapshot exposes Local LLM,
Mock Vision, alignment, and grounding scope without interpreting Mock Vision as real proof.

## 9. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/human-review-tasks` | Tenant queue and filters |
| GET | `/api/v1/human-review-tasks/{task_id}` | Packet, basis choices, actions, decision |
| GET | `/api/v1/cases/{case_id}/human-review-tasks` | Case-scoped queue reuse |
| POST | `/api/v1/human-review-tasks/{task_id}/claim` | Exclusive CAS claim |
| POST | `/api/v1/human-review-tasks/{task_id}/release` | Return to pending |
| POST | `/api/v1/human-review-tasks/{task_id}/request-additional-evidence` | Wait for evidence |
| POST | `/api/v1/human-review-tasks/{task_id}/resume` | Resume after evidence/Admin reason |
| POST | `/api/v1/human-review-tasks/{task_id}/escalate` | Escalate without child task |
| POST | `/api/v1/human-review-tasks/{task_id}/resolve` | Human-only final-decision record |

## 10. Verification

The first table preserves the 0011 functional baseline. The second table records the final 0012
Closeout executed on the completed diff.

| Gate | Actual result |
|---|---|
| Sprint regression | 484 passed, 57 deselected, 31 warnings |
| Ruff | PASS, 0 findings |
| Format | PASS, 315 files |
| Pyright | PASS, 0 errors/warnings/informations |
| Human Review unit/HTTP/runtime | 28 passed |
| Architecture focus | Included in 37 focused passes |
| PostgreSQL repository focus | 2 passed |
| Full integration | 46 passed, 5 external-GPU skipped, 490 deselected, 3 warnings |
| Migration | Three paths PASS, drift 0, temporary DB 0 |
| Docker health | 6/6 healthy |
| Queue | Six application queues, consumer 1 and depth 0 each |
| Live E2E | Task/packet/action/decision/basis counts and auth/idempotency gates PASS |
| Git whitespace | `git diff --check` PASS |

| Final reliability gate | Current result |
|---|---|
| Static checks on final diff | PASS — Ruff 0, Format 324 files, Pyright 0 |
| Default and full integration regression on final diff | PASS — 516 default; 48 integration, 5 external-GPU skipped |
| 0012 empty/previous/downgrade-upgrade migration paths | PASS — three paths, drift 0, temporary DB remaining 0 |
| Broker failure, duplicate delivery, lease expiry and stale-result fencing | PASS — real broker outage recovered; duplicate deliveries `NOOP`; focused reliability tests passed |
| Final Docker health and live Human Review smoke | PASS — Core 6/6 healthy, six queues consumer 1/depth 0, Human Review smoke passed |
| Disposable Human Review/reliability repository focus | PASS — 4 integration tests; temporary DB remaining 0 |

The first repository probe exposed missing explicit flush ordering for ORM aggregates without
relationships; task and decision roots are now flushed before dependent packet/action/basis rows.
The first full regression had eight stale migration-head assertions, not behavior failures; all were
updated to the new linear 0011 head and the full suite passed. A shared-database integration run
also exposed dispatcher/test event contention; the suite now clones the main PostgreSQL database,
runs in a disposable database, drops it, and asserts that none remain. The live database had been
stamped with an intermediate development form of 0012, so the first final downgrade found a missing
constraint. Downgrade was made tolerant of that partial local state and the complete
0012→0011→0012 round trip then passed with drift 0.

## 11. Limitations

- Synthetic rule set and workflow data; no real company-policy or legal validation
- Local LLM remains `LOCAL_POC`; real Vision is not qualified
- No Review UI, external refund/exchange/reshipment/payment/CRM execution, or customer notification
- No final report, decision revision/amendment, automatic assignment, SLA escalation, or packet revision

## 12. Sprint 5C next boundary

Sprint 5C starts from this passed Closeout baseline. It adds a Case-lifecycle-independent CAS
Resolution Projection, append-only Resolution Events, immutable typed Action Intent and a
network-free deterministic External Action `DRY_RUN`. Required parameters may come only from Case
references and explicitly submitted `attributes.external_action_input`; missing or invalid data
ends at `ACTION_NEEDS_INPUT` with no Attempt/Result. `LIVE` execution, Case Closure, Decision
amendment, notification, SLA routing and Review-stage input completion remain explicitly excluded.
