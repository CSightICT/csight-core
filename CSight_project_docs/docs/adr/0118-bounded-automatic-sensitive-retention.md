# ADR-0118: Bounded automatic sensitive retention uses a non-human maintenance capability

- Status: Accepted
- Date: 2026-08-30

## Context

ADR-0108 made sensitive-payload purge an explicit active-tenant-ADMIN operation. That is safe for
recovery and object deletion, but it leaves ordinary retention dependent on a person remembering to
run a destructive command. An expired customer inquiry can therefore remain recoverable after its
approved retention window even though the atomic redaction path already exists.

The limited pilot is one customer deployment. It needs automatic expiry without granting an
unattended process the broader Evidence reconciliation or MinIO deletion capabilities of the
operator tool, and without recording a human administrator as an actor when no human initiated the
run.

## Decision

- An opt-in `privacy-lifecycle` maintenance process may invoke only expired sensitive-payload
  redaction. It cannot obtain the Evidence inventory or version-deletion adapters.
- The process is disabled by default. Enabling it requires an exact tenant UUID plus an explicitly
  configured retention policy version and duration. Local/test defaults do not satisfy the
  automation configuration gate.
- Outside local/test, startup also requires the RLS-enforced API database role. Every sweep binds
  the configured tenant as transaction-local context and opens all-Case read capability only inside
  that tenant-bound maintenance scope; the process cannot enumerate or switch to a second tenant.
- One sweep runs bounded batches and stops immediately on a blocked item. A configured maximum batch
  count prevents a maintenance run from monopolizing PostgreSQL. Remaining truncation is an alert
  state, not success.
- Automated purge writes the same append-only lifecycle receipt as manual purge, with `actor_id`
  null and fixed `initiator=SYSTEM_RETENTION_SCHEDULER`. It never invents or impersonates a human
  administrator.
- Health state contains only low-cardinality aggregate counts and a timestamp. Missing, stale,
  blocked, or truncated state makes the container unhealthy and emits a structured
  `privacy_retention_sweep_attention_required` signal. Customer text, identifiers, hashes, object
  keys, and exception messages are excluded.
- Limited-pilot release evidence must include both a successful automatic retention drill and the
  enabled runtime configuration. A passing unit test or a configured schedule alone is insufficient.
- This decision supersedes ADR-0108 only for ordinary expired sensitive-payload redaction. Manual
  reconciliation and every MinIO deletion remain active-tenant-ADMIN, dry-run-first operations with
  explicit confirmation.

## Consequences

- Expired customer prose and bounded derivatives no longer depend on a daily manual action.
- A digest mismatch or other integrity problem remains visible and blocks the sweep instead of being
  silently skipped.
- The first sweep can run immediately at process start; operators must review the dry-run before
  enabling the profile for a customer tenant.
- Alert delivery, backup expiry, legal hold, and Evidence-object retention remain separate pilot
  gates. This process does not claim those concerns are complete.

## Related decisions

- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0108](0108-retention-purge-and-evidence-reconciliation.md)
- [ADR-0112](0112-customer-derived-analysis-text-erasure.md)
- [ADR-0114](0114-terminal-customer-content-erasure.md)
