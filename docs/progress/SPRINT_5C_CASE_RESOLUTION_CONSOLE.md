# Sprint 5C — Case Resolution, DRY-RUN, and Consultant Console Closeout

## 1. Current verdict and Git handoff

`SYNTHETIC_MOCK_SIMULATION_DEMO`

Sprint 5C is complete as an internal simulation demo. The Case Resolution lifecycle, deterministic
external-action `DRY_RUN`, immutable Review Report, PoC KPI summary, and React consultant console
are implemented and passed the recorded backend, frontend, migration, and live-runtime gates.

This is not a Limited PoC verdict. The remaining promotion work is external evidence acquisition
and qualification, not another claim that the implemented screens or `DRY_RUN` prove real business
performance. Until every gate in
[`SPRINT_5C_DEMO_BOUNDARY.md`](../resolution/SPRINT_5C_DEMO_BOUNDARY.md) is evidenced, the
user-facing label remains “synthetic-data and Mock-Vision-based simulation demo.”

| Item | Current value |
|---|---|
| Sprint 5B baseline | `4aefae6 feat: add human review workflow` |
| Sprint 5B backup | Pushed to `origin/feature/sprint-5b-human-review-workflow` |
| Sprint 5C branch | `feature/sprint-5c-case-resolution-external-action` |
| Sprint 5C feature baseline | `0a5f529 feat: add case resolution and PoC console` |
| Sprint 5C backup / PR | Pushed with this closeout ledger to `origin/feature/sprint-5c-case-resolution-external-action`; no PR |
| User-owned root documents | `CSight_MASTER_HANDOFF_2026-08-27.md` and `kaputt_best_vision_architecture.md` untouched and excluded |

## 2. Resolution and action boundary

Case Resolution is separate from `cases.status`. A Human Decision is immutable and remains the
only final-decision source; Resolution records what should happen after that decision without
closing the Case or changing the Decision.

The versioned mapping is `human_decision_to_external_action/1.0.0`:

| Human Decision | Mapping outcome |
|---|---|
| `APPROVE_REFUND` | `REFUND` |
| `APPROVE_EXCHANGE` | `EXCHANGE` |
| `APPROVE_RESHIPMENT` | `RESHIPMENT` |
| `APPROVE_REPAIR` | `REPAIR` |
| `REJECT_REQUEST`, `NO_ACTION` | `ACTION_NOT_REQUIRED` |
| `PROVIDE_INFORMATION` | `MANUAL_FOLLOW_UP_REQUIRED` |

Resolution owns a row-locked, versioned projection and append-only Events. The implemented states
are `DECISION_RECORDED`, `ACTION_NOT_REQUIRED`, `MANUAL_FOLLOW_UP_REQUIRED`,
`ACTION_NEEDS_INPUT`, `ACTION_READY`, `ACTION_DRY_RUN_PENDING`,
`ACTION_DRY_RUN_VALIDATED`, and `ACTION_DRY_RUN_FAILED`.

Only `cases.order_ref`, `cases.product_ref`, and the explicitly submitted flat
`attributes.external_action_input` object may supply Action parameters. Unknown or nested fields,
coercion, and action-inapplicable fields fail closed. No amount, currency, quantity, or shipping
reference is inferred from order value, customer text, model output, policy text, rationale, or
another Case.

| Action | Required Case fields | Required explicit input |
|---|---|---|
| `REFUND` | `order_ref` | `amount`, `currency` |
| `EXCHANGE` | `order_ref`, `product_ref` | `quantity`, `shipping_address_ref` |
| `RESHIPMENT` | `order_ref`, `product_ref` | `quantity`, `shipping_address_ref` |
| `REPAIR` | `order_ref`, `product_ref` | `quantity` |

Missing or invalid input ends at `ACTION_NEEDS_INPUT`. It creates no Action Intent, simulation
request, Attempt, or Result. A different second Human Decision for the same Case is not treated as
a replacement: the projection moves to `MANUAL_FOLLOW_UP_REQUIRED`, preserves the original
Decision and Intent, and creates no new Intent.

## 3. Atomicity, immutability, and asynchronous reliability

The authenticated Human Review resolve transaction stores the Decision, basis, Review state/action,
initial Resolution projection/event, and `case_resolution.requested.v1` durable event atomically.
The Resolution worker validates the exact event identity and Decision hash before mapping. A
complete assessment creates one immutable, typed, content-hashed Action Intent and one
`external_action.simulation_requested.v1` durable event in the same transaction.

The two new outboxes retain separate delivery lifecycles. They use claim tokens, leases, bounded
publish backoff, terminal failure records, exact-event validation, and idempotent consumers. The
simulation worker uses an execution lease and late-result fencing; duplicate delivery cannot commit
a second Intent, Attempt, or Result.

The adapter is deterministic and network-free. `DRY_RUN` always records
`side_effects_performed=false`; defensive `LIVE` input fails with
`LIVE_EXTERNAL_ACTION_DISABLED` before any provider call. `ACTION_DRY_RUN_VALIDATED` means only that
the immutable command shape passed local simulation checks.

## 4. Review Report and PoC KPI boundary

Every new terminal Resolution version atomically creates one immutable
`review_report/1.0.0` snapshot. The latest report is returned for a Case, its content hash is
revalidated on read, and a later terminal Resolution version may create a new append-only report.
The snapshot uses structured database records and excludes raw model input/output and hidden
reasoning. If a durable failure transition is caused by a corrupt or missing source graph, a
bounded degraded integrity snapshot preserves the terminal failure instead of rolling the
transaction back.

The tenant-scoped `poc_summary/1.0.0` endpoint exposes numerator, denominator, sample count, and a
nullable value for every KPI:

| KPI | Implemented definition |
|---|---|
| Review time | Sum of completed claim intervals divided by resolved Review Task count |
| Recommendation difference | Decisions marked different divided by comparable Decisions only |
| Additional evidence | Tasks that ever requested evidence divided by all Review Tasks |
| Missing Action input | `ACTION_NEEDS_INPUT` approval Resolutions divided by the four approval Decision Resolutions |
| `DRY_RUN` success | Validated Results divided by validated plus failed simulation Results |
| Analysis failure | Failed terminal Analysis Runs divided by terminal Analysis Runs |
| Analysis partial success | Partial-success terminal Analysis Runs divided by terminal Analysis Runs |

A zero denominator produces `value: null`, not a fabricated zero rate. These KPIs are descriptive
for the current synthetic/Mock scope and do not establish savings, ROI, or real-user performance.

## 5. Read-only API and consultant console

Sprint 5C adds authenticated, tenant-scoped, `no-store` reads only:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/cases/{case_id}/resolution` | Current Resolution projection |
| `GET` | `/api/v1/cases/{case_id}/resolution/events` | Ordered append-only Resolution Events |
| `GET` | `/api/v1/cases/{case_id}/external-action-intents` | Immutable Case Action Intents |
| `GET` | `/api/v1/external-action-intents/{intent_id}` | Intent, Attempts, and Results |
| `GET` | `/api/v1/cases/{case_id}/review-report` | Latest immutable Review Report |
| `GET` | `/api/v1/metrics/poc-summary` | Tenant-scoped PoC KPI summary |

The React 19, TypeScript, and Vite console implements login, Case create/list/detail, Evidence
upload, analysis and policy-workflow progress, Top-3 citations, Review queue/detail/actions,
qualification badges, Resolution/Intent/`DRY_RUN` views, printable Review Report, and PoC metrics.
The browser uses the Web service's `/api` proxy. JWT access tokens stay in memory; session storage
contains only validated opaque workflow IDs and idempotency keys so a user can reauthenticate and
resume existing idempotent runs. No server-side Workflow Coordinator was added.

### 5.1 Human-confirmed PoC quick review extension

The Review detail screen additionally offers two primary actions, `ALLOW` and `DENY`, when the
deterministic quick-review readiness score reaches `0.70`. This is a contract-readiness score, not a
model confidence or accuracy metric. It assigns `0.35` to the human-review policy state, `0.25` to
an immutable rule basis, `0.15` to an immutable citation, `0.10` to qualification metadata, and
`0.15` to one unambiguous `MARK_REVIEW_ELIGIBILITY` mapping.

The authenticated user's click composes the existing CAS claim and resolve APIs. `ALLOW` maps only
from packet-contained policy eligibility to the existing typed approval Decision; `DENY` maps to
`REJECT_REQUEST`. The browser automatically attaches the first immutable rule and citation, records
a transparent fixed rationale, waits for the existing Resolution/DRY-RUN workers, and opens the
immutable `review_report/1.0.0` when available. Additional-evidence states and Admin-only tasks still
fail closed. Customer prose, Vision score, LLM output, and requested-action inference are not used
to choose the Decision type. The detailed form remains available as an exception path.

This extension adds no server-side coordinator, new mutation API, model-created Decision, `LIVE`
action, or Case closure. Its accepted boundary is recorded in
`CSight_project_docs/docs/adr/0097-human-confirmed-poc-quick-review.md`.

### 5.2 Reference-informed refund processing confirmation

An `APPROVE_REFUND` Decision or immutable `REFUND` Action Intent now selects a dedicated
`환불 처리 확인서` instead of the generic snapshot viewer. The document is informed by common
operational fields from official Shopify refund guidance, Stripe refund lifecycle documentation,
and Korean e-commerce refund/cancellation requirements. It does not copy a real company's visual
identity or represent an executed payment transaction.

The view contains the order and product reference, amount/currency/quantity, refund reason, human
approval, policy version, payment-provider cancellation request, customer notification, return
authorization/tracking, processing timeline, and immutable audit identifiers. Values are read only
from `review_report/1.0.0`; missing inputs remain missing. `ACTION_NEEDS_INPUT` says no request was
created, while `ACTION_DRY_RUN_VALIDATED` says only that the request shape was validated. Every
variant visibly states that the external payment, refund, collection, and notification side effects
were not performed.

The field rationale, source links, and production limitations are recorded in
[`REFUND_PROCESSING_CONFIRMATION.md`](../resolution/REFUND_PROCESSING_CONFIRMATION.md).

## 6. Migration

| Revision | Purpose |
|---|---|
| `20260827_0013_case_resolution_external_action` | Resolution projection/events, immutable Intent, simulation Attempts/Results, and two durable outboxes |
| `20260827_0014_review_report_poc_metrics` | Immutable Review Report snapshot storage and related integrity constraints |

The final PostgreSQL head is `0014`. Empty-to-head, previous-to-head, downgrade/upgrade lifecycle,
and schema drift checks passed; final drift is 0.

## 7. Verification evidence

| Gate | Final observed result |
|---|---|
| Backend default suite | PASS — 554 passed, 62 deselected |
| Backend integration suite | PASS — 51 passed, 5 external-GPU skipped, 560 deselected |
| Backend static checks | PASS — Ruff, format, and Pyright |
| Frontend static/contracts | PASS — lint, TypeScript, generated OpenAPI check, and production build |
| Frontend component/unit | PASS — Vitest 6 |
| Frontend browser scenarios | PASS — Playwright 5 |
| Refund confirmation extension | PASS — TypeScript, ESLint, build; Vitest 17 files/49 tests; Playwright 5; 1440px full-page visual QA |
| PostgreSQL migration | PASS — head `0014`, drift 0 |
| Runtime health | PASS — 7 services healthy |
| Queue topology | PASS — 8 application queues, each consumer 1 and depth 0 |
| Live causal path | PASS — Human Decision → Resolution → deterministic `DRY_RUN` → `ACTION_DRY_RUN_VALIDATED` |
| Live replay and isolation | PASS — duplicate `NOOP`, Case status unchanged, cross-tenant read `404` |
| Real broker outage | PASS — Resolution event stayed `PENDING` through attempt 3, recovered to `CONSUMED` at attempt 5, and the final Resolution validated |

The disposable PostgreSQL integration path additionally verified atomic Decision/Resolution
creation, exact-event processing, missing input with zero Intent/Attempt/Result, conflicting second
Decision fail-closed behavior, immutable report creation/replay, tenant report isolation, report
hash-tamper rejection, and KPI numerator/denominator/sample-count calculations.

## 8. Five internal demo scenarios and evidence level

The five Playwright scenarios use deterministic intercepted API fixtures. They prove that the
implemented UI renders and enforces the expected component behavior; they are not, by themselves,
live backend causal E2E evidence. Backend/runtime evidence is listed separately below.

| # | Scenario | Current evidence | Honest interpretation |
|---:|---|---|---|
| 1 | Complete Repair → Decision → `DRY_RUN` validated | Live backend/runtime causal path, disposable PostgreSQL integration, fixture-driven Playwright UI | Full backend causal flow was observed; the Playwright browser layer is fixture-driven |
| 2 | Refund missing amount/currency → `ACTION_NEEDS_INPUT`, zero Action rows | Disposable PostgreSQL integration and fixture-driven Playwright UI | Backend persistence invariant and UI state are covered; no live browser-to-runtime causal run was recorded |
| 3 | Missing image → request additional evidence, zero Decision/Action | Fixture-driven Playwright UI plus existing Human Review component/state tests | UI/component-backed only for this five-scenario demo; not a recorded live causal E2E |
| 4 | Safety Case → Reviewer blocked, Admin resolve available | Fixture-driven Playwright UI plus backend authorization tests | UI/component and backend rule coverage exist, but this scenario was not recorded as one live browser causal chain |
| 5 | Vision timeout → Partial Success/Human Review, zero automatic Decision/Action | Fixture-driven Playwright UI plus existing backend Mock-Vision partial-success tests | UI/component and backend-path coverage exist separately; not a recorded live causal E2E |

Accordingly, “Playwright 5 passed” must not be restated as “five live end-to-end business flows
passed.” Scenarios 3–5 remain specifically fixture-driven UI/component-backed demonstrations.

## 9. Explicit exclusions and remaining Limited PoC gate

Sprint 5C does not provide actual `LIVE` execution, payment/refund/exchange/reshipment/repair/CRM or
notification integration, Case Closure, Decision amendment, Review-stage input completion,
automatic assignment/SLA, OIDC, or RLS.

Promotion to `LIMITED_POC` still requires all external evidence and approvals below:

- a confirmed customer candidate, one product category, and two or three defect types;
- at least 30 de-identified real Cases with counselor/domain-expert Gold;
- versioned real company policy with effective dates and real policy/Case/query-distribution
  evaluation;
- approved retention, deletion, EXIF removal, and access-control handling;
- real Vision qualification with model/dataset/taxonomy/threshold/pre/postprocess evidence, or an
  explicit approved Vision exclusion scope;
- Qwen3.8 Extraction and Grounding reevaluation on the intended real distribution;
- completed Shadow Mode comparison against Human Gold;
- machine-verifiable zero counts for cross-tenant access, unauthorized Decision, duplicate
  Intent/Result, `LIVE` execution, parameter inference, premature closure, and Decision mutation;
  and
- backend/frontend regression plus a clean-environment five-scenario demo tied to the release.

At this closeout point the actual `LIVE` path, real data and policy, real Vision qualification,
privacy approval, Shadow comparison, and real Qwen reevaluation remain unavailable or not run.
Therefore the Limited PoC gate is not satisfied, and performance or ROI must not be presented as an
actual PoC result.

## 10. Canonical references

- [Case Resolution Architecture](../resolution/CASE_RESOLUTION_ARCHITECTURE.md)
- [Case Resolution State Machine](../resolution/CASE_RESOLUTION_STATE_MACHINE.md)
- [External Action Contract](../resolution/EXTERNAL_ACTION_CONTRACT.md)
- [Demo Boundary and Limited PoC Gate](../resolution/SPRINT_5C_DEMO_BOUNDARY.md)
- [Current Status](CURRENT_STATUS.md)
