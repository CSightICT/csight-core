# ADR-0110: Waiting-review ownership and similarity reference distance

- Status: Accepted
- Date: 2026-08-30
- Clarifies: ADR-0109
- Related: ADR-0077, ADR-0078, ADR-0083, ADR-0101

## Context

ADR-0109 introduced administrator-managed review assignment and explanatory policy-similarity groups. Two details remained unsafe or ambiguous in the implementation.

First, requesting more evidence moved a claimed task to `WAITING_FOR_EVIDENCE`, closed its assignment interval, and cleared its assignee. The work then disappeared from both reviewer menus and lost the owner who was expected to resume it.

Second, the console called the `NEAREST` group closest to the `0.65` reference while the builder selected the highest cosine scores. The use of truth-value fallback also converted the valid cosine value `0.0` into `-1.0`.

## Decision

1. `WAITING_FOR_EVIDENCE` is a non-terminal state owned by the current assignee. Requesting evidence preserves both `current_assignee_id` and the active append-only assignment interval.
2. Resuming a waiting task returns it directly to `CLAIMED` with the same owner. The owner may resume it; an administrator may perform an explicit override without silently changing ownership.
3. Existing waiting rows are recovered additively from their latest historical assignment. Recovery appends a new active `WAITING_OWNER_RECOVERY` interval and never rewrites a historical release timestamp. Migration fails closed when no prior owner can be recovered.
4. The `NEAREST` similarity group means the three eligible clauses with the smallest absolute distance from the versioned cosine reference `0.65`. Ties prefer the higher cosine and then deterministic clause identity.
5. The `LEAST` group means the three eligible clauses with the lowest cosine similarity. It remains retrieval-distance evidence, not a policy-rule rejection or a training label.
6. Cosine `0.0` is valid evidence. Only an absent score (`None`) may use a fallback sentinel.
7. These groups remain explanatory and do not change the fixed `RAW -> HYBRID -> Top 3` policy-decision path. Only an authenticated human can create a final decision.

## Consequences

- A review waiting for evidence remains visible to exactly one current owner and can be resumed without a claim race.
- Historical waiting tasks receive explicit recovery provenance instead of mutated history.
- API, database ordering, tests, and Korean UI wording share one definition of “reference-nearest.”
- Retrieval performs the existing exact comparison query but makes no additional model-provider call and stores no inquiry embedding.
- No refund, payment, email, shipment, or other external business side effect is introduced.
