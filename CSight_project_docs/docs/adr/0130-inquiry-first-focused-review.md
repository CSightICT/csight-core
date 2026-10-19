# ADR-0130: Inquiry-first queues and focused consultant review

- Status: Accepted
- Date: 2026-09-11
- Authority: Owner requested UI simplification following technical mentoring.
- Extends: ADR-0097, ADR-0101, ADR-0109; no decision or policy changes.

## Decision

Queues lead with a bounded excerpt of the inquiry rather than product identity. Add optional
`inquiry_preview` (at most 160 characters) to both operator read projections and HTTP responses.
Read it in the existing single SQL statement from tenant-bound, unexpired, non-purged sensitive
payloads. Normalize whitespace without calling a model or storing another copy. No legacy raw-text
fallback. Missing/expired excerpts fall back to the declared request type in the UI. Existing
ownership, counts, cursors, reference search, and no-store response semantics remain unchanged.

A Case with an unresolved review task links directly to its review. Other Cases retain the
workspace route. Review detail offers a link back to workflow details.

The default review surface shows photos, small product/code/payment context, the stored inquiry
summary, numeric quick-review threshold, and human allow/deny controls. Missing commerce values
remain missing; fictional amounts are labelled and never become external-action inputs.
Inquiry original, policy evidence, qualification metadata and technical provenance are available
through disclosures; similarity diagnostics use a nested disclosure. Missing summaries open the
original automatically. Important loading, authority and decision blockers remain visible.

The numeric threshold is the existing quick-review readiness gate (0.70), not E3's threshold,
policy cosine similarity, model confidence or measured accuracy. Readiness is separately labelled.
No gauge is rendered. Mapping, evidence-decode gates, CAS ownership, explicit second confirmation,
append-only decisions and simulated external execution remain unchanged.

## Consequences

No database schema or stored-data change: no migration is required. Rollback uses the prior API/UI;
the new response field is optional and no history is rewritten. API snapshots/types and contract,
SQL, frontend and browser checks accompany the change. Sensitive excerpts never enter logs or
persistent browser storage. Existing expiry and tenant access boundaries apply.

The intended benefit is less navigation, reading and manual record preparation. Actual handle-time
reduction and decision quality require a controlled human comparison; this change asserts neither
customer ROI nor model qualification.


## 2026-09-11 owner refinement

Customer, product/order, original inquiry and fixed-policy details move below the primary
photo/summary/decision layout and are closed initially (original opens when summary is missing).
This supersedes the small product/payment caption on the default surface. A ready unresolved
Case URL opens its matching review directly; `?details=1` explicitly accesses processing details
without redirect loops. Pre-review and completed workspaces also collapse customer/product/order
and fixed-policy evidence below the workbench. Final confirmation and decision guards are unchanged.
