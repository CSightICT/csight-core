# ADR-0111: Case intake assignment and direct-object ownership

- Status: Accepted
- Date: 2026-08-30
- Extends: ADR-0109, ADR-0110
- Related: ADR-0077, ADR-0078, ADR-0105

## Context

Review ownership previously began only after policy evaluation created a human-review task. An
incoming Case could therefore remain tenant-visible without an accountable owner, and a reviewer
who knew a Case or Evidence identifier could use several legacy detail APIs outside the operator
queue's personal-work filter. Assigning only the review task also meant that intake ownership and
review ownership could diverge.

## Decision

1. Assignment begins on the Case, before analysis or policy execution. `cases` keeps the current
   assignee and a compare-and-swap assignment version; append-only assignment intervals and action
   events preserve the history.
2. Only an authenticated administrator may assign or reassign a non-terminal Case. The target must
   be an active administrator or reviewer in the same tenant. A stale version returns a conflict.
3. Assigning a Case atomically moves every unresolved human-review task to the same owner. Pending
   or escalated tasks become claimed; waiting tasks retain their waiting state and ownership.
4. A reviewer can read a Case and its Case-scoped objects only while currently assigned, or after
   the reviewer has created that Case's final human decision. Unauthorized and cross-tenant direct
   identifiers return `404`. Administrators and quality viewers retain tenant-scoped read access.
5. API enforcement is paired with restrictive PostgreSQL `SELECT` policies using transaction-local
   actor and privileged-read context. Removing an application `tenant_id` or owner predicate must
   still return zero unauthorized rows.
6. The operator Case projection returns the assignment version in the same list query. The admin UI
   assigns from the intake queue and does not fetch one assignment detail per row.
7. Assignment never creates a policy decision, final human decision, refund, payment, email,
   shipment, or other external business side effect.

## Consequences

- A new inquiry can have one accountable owner before model or policy processing succeeds.
- Reassignment immediately removes active visibility from the former owner and transfers any open
  review without split ownership.
- Existing review ownership is backfilled additively; historical review and assignment events are
  not rewritten.
- Direct-object authorization now depends on request-scoped actor context, so every new Case-scoped
  table and route must make an explicit ownership-policy decision.
