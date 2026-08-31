# ADR-0112: Customer-derived analysis prose is redactable while execution lineage stays immutable

- Status: Accepted
- Date: 2026-08-30

## Context

ADR-0108 removed expired customer prose from the restricted payload and legacy Case column but
deliberately left append-only analysis results unchanged. That boundary retained exact LLM source
quotes, summaries, generated retrieval queries, grounded explanations, and provider failure text
after the source inquiry expired. Keeping those strings would make the retention operation a partial
tombstone rather than deletion of customer-derived analysis text.

Blindly deleting analysis rows would also destroy the evidence that a run happened and which model,
prompt, policy, threshold, embedding, and index versions were used. Rewriting immutable human
decisions, terminal reports, or customer communication simulations without a separate legal-retention
and hash-lineage contract would make their integrity checks misleading.

## Decision

Migration `20260830_0027_analysis_text_erasure` introduces a narrow privacy exception to content
immutability while preserving execution lineage:

- `case_sensitive_payloads.analysis_text_purged_at` must be null for an active payload and equal
  `purged_at` after retention erasure;
- the same transaction that clears raw prose also clears LLM v1/v2 claims, exact source quotes,
  extracted action quotes, ambiguity and missing-information arrays, and replaces summaries with the
  fixed `[PURGED_BY_RETENTION]` tombstone;
- generated policy queries are replaced by the fixed tombstone while their original one-way query
  hash, run identity, strategy, profile, index, rank, and similarity lineage remain;
- grounded policy statements and unresolved-condition prose are cleared and validation counts are
  reset, while citation packs retain only versioned company-policy text and provenance;
- analysis, retrieval, and grounding provider failure messages are replaced by the fixed tombstone;
- the PII-free lifecycle event records bounded per-table row counts and
  `analysis_text_redacted=true`, never the removed values;
- existing already-purged rows are redacted during upgrade before the stronger check is installed;
- deferred PostgreSQL triggers reject any non-tombstoned derived prose or provider failure text
  inserted or restored for a purged Case; and
- downgrade is refused once analysis text has been redacted because the removed prose cannot and
  must not be reconstructed.

Run/stage/attempt IDs, statuses, timestamps, token counts, model/prompt versions, policy and index
references, opaque request hashes, policy corpus citations, similarity values, and human-final-decision
boundaries remain immutable. The normal application repositories still expose no update/delete method
for analysis results; only the authenticated, dry-run-first privacy lifecycle maintenance path performs
the bounded redaction.

Human-entered rationale, terminal Review Report snapshots, communication simulations, Case commerce
attributes, backup expiry, and legal holds are not silently folded into this decision. They require a
separate retention class and a redaction receipt/hash-verification contract before mutation.

## Consequences

- Expiring a Case no longer leaves exact inquiry quotes in primary LLM analysis, generated search
  text, grounded explanations, or related failure messages.
- Historical model and policy qualification remains possible from identifiers, versions, metrics,
  ranks, and hashes, but the erased prose cannot be replayed or used as a learning asset.
- A purged result remains schema-readable as a tombstoned projection; new analysis and retrieval were
  already rejected after raw payload purge by ADR-0108.
- This closes the primary model/search derivative gap but does not make the whole tenant erasure
  program complete. Terminal business records, attributes, logs, backups, and legal holds remain
  explicit release blockers.

## Related decisions

- [ADR-0102](0102-sensitive-payload-lifecycle-expand-phase.md)
- [ADR-0108](0108-retention-purge-and-evidence-reconciliation.md)
- [ADR-0111](0111-case-intake-assignment-and-direct-object-ownership.md)
