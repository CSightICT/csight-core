# ADR-0108: Expired prose is tombstoned atomically and Evidence repair is dry-run first

- Status: Accepted
- Date: 2026-08-29

## Context

ADR-0102 introduced an additive `case_sensitive_payloads` boundary but deliberately retained
`cases.customer_message` for compatibility. Purging only the restricted row would therefore leave
the same customer prose in the legacy column and would not be erasure. PostgreSQL and MinIO also do
not share a transaction, so stale `PENDING` rows, missing objects, failed-row objects, and objects
without a matching Evidence row must be reconciled without silently deleting storage.

Removing the legacy column is not rollback-safe yet. The limited pilot instead needs a smaller
contract step that removes expired content from both copies while preserving the operational Case
shell and a PII-free audit trail.

## Decision

Migration `20260829_0022_privacy_lifecycle` is a fail-closed follow-up contract:

- upgrade stops when any Case lacks a sensitive-payload row or an active dual write differs;
- deferred PostgreSQL constraint triggers require every Case to have exactly one matching active
  payload, or a purged payload plus the fixed `[PURGED_BY_RETENTION]` legacy tombstone;
- operational Case reads no longer fall back to `cases.customer_message` when the restricted row is
  missing or purged;
- the legacy column remains present and non-null for one-release response compatibility;
- an expired purge locks the Case and payload, verifies expiry, digest, and dual-write parity, then
  clears restricted prose, replaces legacy prose with the fixed tombstone, records both purge
  timestamps, and appends `SENSITIVE_PAYLOAD_PURGED` in one transaction; and
- downgrade refuses to proceed after a purge because raw prose cannot and must not be reconstructed.

The Evidence consistency job is tenant-scoped and defaults to read-only `DRY_RUN`:

- a stale `PENDING` row with matching object metadata is promoted to `AVAILABLE`;
- stale `PENDING` or `AVAILABLE` rows with missing/mismatched objects are marked `FAILED`;
- objects attached to `FAILED` rows and canonical objects with no Evidence row are deletion
  candidates;
- mutation requires `--execute` plus an exact tenant confirmation;
- object deletion additionally requires `--delete-orphan-objects`;
- `EVIDENCE_PURGE_REQUESTED` is committed before MinIO deletion and `EVIDENCE_PURGED` after success;
- deletion inventories the exact object key with MinIO version listing, removes every payload version
  and delete marker by opaque version ID, then inventories the key again;
- a failed or truncated version inventory, deletion error, or any remaining version blocks completion,
  so deleting only the current key can never be reported as erasure;
- each DB recovery appends `EVIDENCE_RECONCILED`; and
- malformed keys or objects whose tenant/Case cannot be attributed are never automatically deleted.

Every lifecycle event uses a bounded, deterministic operation key and fixed low-cardinality details.
It contains resource identifiers, state names, reason codes, and `pii_included=false`; it never
contains customer prose, filename, object bytes, signed URL, credential, or exception message.
The API and Worker database roles have `UPDATE` and `DELETE` revoked on the lifecycle table, so
runtime access is append-only. The schema-owner/migration connection remains an explicitly governed
maintenance capability and is not an application runtime credential.

Only an active tenant `ADMIN` reloaded from the identity repository may run the command. Production
still requires an explicit tenant retention version and duration; local/test alone retain the
30-day development default.

## Consequences

- Expired customer prose is removed from both persisted copies without rewriting Case identity,
  workflow history, digest tombstone, or append-only analysis results.
- A retained Case can still be listed, but new text analysis or retrieval is rejected after its
  prose is purged.
- The fixed tombstone is an operational compatibility value, not customer content and not model
  input.
- Storage erasure is permanent and auditable but not atomic with PostgreSQL. A delete failure leaves
  a durable request event and a safe blocked result for operator retry; a completion event is written
  only after a zero-version recheck.
- Bounded inventory pages report `truncated=true`; a truncated run is not proof of full consistency.
- ADR-0112 removes primary LLM/search/grounding prose while retaining execution lineage. Full removal
  of `cases.customer_message`, human/terminal report prose, automated scheduling, evidence retention
  expiry, backup expiry, and legal-hold handling remain separate contract migrations. This ADR does
  not claim those are complete.

## Related decisions

- [ADR-0007](0007-private-evidence-storage-and-compensation.md)
- [ADR-0102](0102-sensitive-payload-lifecycle-expand-phase.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0112](0112-customer-derived-analysis-text-erasure.md)
