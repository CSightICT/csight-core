# Citation Pack and Grounding Guardrails

Sprint 4C-3A turns one successful policy retrieval run into an immutable Citation Pack and a
decision-free grounded explanation run.

## Flow

`Successful retrieval → immutable Citation Pack → run + outbox → identifier-only queue → provider →
strict schema → citation allowlist validator → append-only result`.

Citation Pack items snapshot `retrieval_run_id`, tenant, rank, policy clause row/public ID, document
ID/version, title, section path, clause type/text, effective interval, source type/hash, HYBRID mode,
query strategy, matched query IDs, and retrieval profile hash. Public API responses omit tenant and
internal clause row IDs.

Each policy statement must contain one or more pack-local `CIT-NNN` identifiers. Extra fields are
forbidden, the summary is fixed and neutral, citation duplicates normalize deterministically, and an
unknown citation fails the run before result persistence. Pack creation rechecks ACTIVE status and
the retrieval run's as-of effective interval.

The queue contains only event, tenant, Case, grounded-run, and correlation IDs. Raw prompts,
responses, reasoning, customer text, clause text, keys, and tokens are not queued or logged. The
result stores only validated structure, metrics, and provider/model/prompt/validator provenance.

This stage does not decide policy applicability, approval, rejection, refund, exchange, fraud,
responsibility, liability, routing, or a final outcome.
