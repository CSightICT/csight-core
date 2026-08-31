# ADR-0114: Terminal customer content erasure with integrity-preserving receipts

- Status: Accepted
- Date: 2026-08-30
- Owners: CSight Platform and Privacy
- Supersedes: none
- Extends: ADR-0108 and ADR-0112

## Context

ADR-0108 deletes expired inquiry text and private Evidence objects, and ADR-0112 removes customer-derived
LLM, retrieval, grounding, and provider-failure prose. Terminal workflows still copied customer display,
contact, shipping, free-form reviewer rationale, and simulated communication content into Case attributes,
human-review audit rows, immutable Review Reports, and communication simulations. Removing only the source
payload therefore did not make the content unrecoverable.

At the same time, a customer-support product must retain the non-content audit lineage that proves who made a
decision, which policy and model versions were used, what terminal state was reached, and that no external
business action occurred.

## Decision

When a Case sensitive payload expires, the authenticated Admin lifecycle transaction must also:

1. replace human decision and review-action rationale with `[PURGED_BY_RETENTION]` and remove free-form action
   payloads;
2. remove all Case attributes after the workflow is terminal;
3. remove customer commerce, order, address, and contact snapshots from every Review Report, while retaining
   Case/Report/Decision IDs, product reference, state, reason codes, policy/model versions, qualification
   metadata, and dry-run outcome metadata;
4. replace simulated communication recipient, subject, and body with the same tombstone;
5. replace Case-resolution failure prose with the tombstone;
6. recompute the current human-decision, Review Report, and communication content hashes; and
7. append a PII-free lifecycle event containing resource counts, before/after opaque hash transitions, the
   redaction policy version, and a deterministic receipt digest.

The `case_sensitive_payloads.terminal_content_purged_at` projection must equal `purged_at`. Deferred PostgreSQL
constraint triggers reject a commit if customer-derived terminal content is restored or if a new unredacted
terminal row is inserted after expiry. Normal domain repositories remain append-only; the only mutation path is
the bounded Admin privacy lifecycle adapter.

## Retention classes

- Deleted at Case-content expiry: customer inquiry prose, model-derived prose, human free-form rationale,
  review action payloads, Case attributes, customer/order/delivery snapshots in reports, simulated customer
  communication text, and resolution failure prose.
- Retained as operational/audit metadata: opaque entity IDs, timestamps, status transitions, staff identity,
  decision type and reason codes, policy citations and versions, model/prompt/index versions, qualification
  measurements, product reference, monetary/quantity dry-run facts, and `side_effects_performed=false`.
- Not resolved by this ADR: tenant onboarding retention approval, scheduler and alerts, log-wide marker scans,
  backup expiry and legal hold, and any separately approved transactional retention for order references.

## Consequences

- A historical report remains readable and hash-verifiable after redaction, but it no longer renders customer
  contact, delivery, order-reference, reviewer prose, or communication content.
- Hash changes are explicit privacy transformations, not silent history rewriting. The pre/post transition is
  recorded without storing the removed content.
- Downgrade is refused once terminal content has been erased because the removed values cannot be restored.
- Human final-decision ownership and the prohibition on actual refund, payment, email, and shipping side
  effects are unchanged.

## Verification

- Blank database and 0028-to-0029 migration lifecycle with Alembic drift zero.
- Actual PostgreSQL workflow: decision, terminal report, communication simulation, expiry purge, readable
  redacted aggregates, synthetic marker count zero in covered stores, and deferred rejection of reinsertion.
- Default tests remain network- and GPU-free.
