# ADR-0129: Audited fixture repair and disposable integration databases

- Status: Accepted
- Date: 2026-09-10
- Authority: Owner requested inspection and correction of inconsistent database data.

## Decision

The live audit found seven legacy test Evidence rows marked AVAILABLE whose objects do not exist,
and seventeen test Cases without intake status history. All are in UUID-named `analysis-` tenants;
the current `csight` tenant is not affected by these findings. The fixed fixture timestamp and
metadata match the analysis test-fixture pattern, not proof of actual customer image loss.

Migration 0038 is a bounded, schema-owner data repair of the seven explicitly audited Evidence IDs.
It verifies their fixture fingerprint and absence of analysis-image references under row locks,
marks AVAILABLE as FAILED, and appends existing EVIDENCE_RECONCILED receipts atomically. The receipt
uses a null human actor and names schema maintenance as initiator. No account or human authentication
is fabricated. No object is created, deleted, restored, or inferred. All other Evidence is untouched.
An absent target is a no-op on other databases; a changed target aborts the migration. An already
repaired target must have its repair receipt. Object absence was observed before migration, not
inferred merely from a database status. This is a fixed audited repair, not a general-purpose
replacement for the active-ADMIN, dry-run-first reconciliation contract of ADR-0108.

Downgrade preserves corrected data and receipts: it must not relabel a nonexistent image AVAILABLE.
There is no schema change. Take and restore-check a fresh database backup before live application.

Missing intake events cannot be reconstructed as genuine historical actions. The seventeen rows
remain explicit unresolved fixture residue pending the separately requested reset/archive scope.
Do not invent case_created events, backdate actions, change immutable source scope, or delete
analysis/human decisions to make an integrity report appear clean.

All opt-in pytest integration tests must target the disposable database created by the official
integration runner. Collection rejects the demo database before any fixture executes. The guard
checks the exact random database name against the runner capability, rather than trusting the
RUN_CORE_INTEGRATION flag alone. The runner still restores a clone and removes only its own database.

## Boundaries

- Models, PRIMARY admission, policy and human decisions, privacy retention, and GPU services are unchanged.
- This does not authorize a global reset, tenant/account deletion, or fake test images.
- A repeatable read-only audit distinguishes relational constraints, mutable projections, and physical
  Evidence availability; historical fixture gaps remain visible independently of repair success.
