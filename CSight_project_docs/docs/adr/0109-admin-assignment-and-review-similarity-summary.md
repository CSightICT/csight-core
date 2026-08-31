# ADR-0109: Admin-managed assignment and review similarity summary

- Status: Accepted
- Date: 2026-08-30
- Supersedes: the operator-facing self-claim-first presentation in ADR-0097; the legacy claim API remains additive for one compatibility release
- Related: ADR-0077, ADR-0078, ADR-0083, ADR-0101, ADR-0103

## Context

The limited-pilot console exposed a tenant-wide case queue to every reviewer and divided the immutable review packet across four technical tabs. That made ownership unclear and forced a reviewer to translate retrieval internals before acting. The existing append-only assignment table already supported administrator assignment provenance, but no administrator API or console control used it.

Policy retrieval also persisted only the fused Top-3 citations. That is sufficient for the policy engine, but it cannot explain which clauses were semantically closest when every result falls below a display reference, or which clauses were clearly inappropriate. Query vectors and raw inquiries must not be retained to solve this presentation problem.

## Decision

1. An authenticated administrator assigns or reassigns an unresolved review task with optimistic concurrency. Every change appends an `ASSIGNED` or `REASSIGNED` action and an `ADMIN_ASSIGNMENT` row; previous assignments are released rather than overwritten.
2. A reviewer-only account sees active cases currently assigned to that user under `문의 대기`. Completed inquiries are separated under `내 문의 처리 현황` and are selected by immutable `human_review_decisions.decided_by` ownership. Administrators retain tenant-wide queues and may change the assignee.
3. Review detail is presented as one summary containing evidence images, the extracted inquiry summary, grounded policy explanation, cited clause text, and compact technical provenance. Final decisions remain authenticated human actions governed by ADR-0077 and ADR-0101.
4. New HYBRID retrieval runs append exact dense-cosine evidence for the three nearest and three least-similar eligible clauses. The reference value `0.65` is versioned as `policy_similarity_reference/1.0.0`, is explanatory only, and is not an eligibility, approval, rejection, or policy-engine threshold.
5. The least-similar list states that low cosine similarity and policy-context mismatch make the clause inappropriate. It is evidence for human understanding, not a negative training label.
6. No raw inquiry, inquiry embedding, or provider response is stored in the similarity table. Existing runs are not backfilled with invented scores; the console explains that a new analysis run is required for exact comparison evidence.

## Consequences

- Review ownership is explicit and administrator corrections remain auditable.
- Reviewer queues fail closed to personal work while quality-viewer and administrator read contracts remain available for oversight.
- Retrieval performs one additional exact ordered query per planned query. Model-provider calls do not increase because the existing query embedding is reused.
- The six similarity rows are append-only run provenance. They do not change the fixed `RAW -> HYBRID -> Top 3` decision path or introduce automatic model substitution.
- No refund, payment, email, shipment, or other external business side effect is added.
