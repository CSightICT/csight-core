# ADR-0127: Explicit retrieval diagnostics and legacy Dev-only evaluation

- Status: Accepted
- Date: 2026-09-09
- Scope: offline scoring contracts and legacy evaluation tools; no release or runtime activation

## Context

Mentoring questions F04/I01 require detecting a retrieved main policy with a missing exception.
Legacy fields named Recall counted any relevant hit, not the fraction of required Gold clauses.
Empty Gold and duplicate ranked hits could also produce misleading scores. The old generic query
CLI evaluated both Dev and Test by default and overwrote its fixed result directory. The MLX tool
also reused historical output paths. These are unsuitable for iterative quality-first diagnostics.

The frozen candidate v1 contract and its RAW 0.975 baseline already use case HitRate semantics.
Changing that contract in place would silently reinterpret historical evidence and admission gates.

## Decision

- Add a pure `retrieval_ranking_metrics/1.0.0` contract. At K=1/3/5/10/20 report case HitRate,
  macro clause Recall, and exact Gold coverage separately. Report MRR@10, binary-relevance nDCG@10,
  zero-result rate and success/failure counts. Failed cases remain in the macro denominator.
- Require nonempty Gold and unique, nonblank record/clause identifiers. Reject duplicate ranked
  hits and failed observations containing hits; revalidate copied model instances. Empty-Gold
  no-answer cases need a separate evaluation contract, not an automatic perfect score here.
- Preserve candidate `query_candidate_metrics/1.0.0` serialization, formula and thresholds.
  Its `recall_at_10` remains historical CASE_HIT_RATE, not clause Recall. Add a distinctly versioned
  `query_retrieval_diagnostics/1.0.0` API; it cannot replace or qualify the frozen candidate report.
- Generic Query Builder and local MLX CLIs become Dev-only diagnostic tools. Refuse Test, old
  freeze and sealed-Test flags before settings, dataset or provider access. Remove automatic
  strategy/profile freezing and unreachable legacy overwrite/freeze helpers. Keep the separate
  candidate-scoped qualification harness unchanged; it does not gain permission to run Test.
- Require a caller-specified, nonexistent run directory before provider construction; refuse
  existing directories, including empty directories and leaf symlinks. Reserve mode 0700 and use
  exclusive creation of 0600 JSON files. Never overwrite old result/profile files or change RAW
  runtime defaults. A failed reserved directory is retained and cannot be reused.
- New wrapper report schemas are `query_builder_dev_evaluation/2.0.0` and
  `local_mlx_dev_evaluation/2.0.0`, with `release_eligible=false` and `profile_frozen=false`.
  Observations contain hashes, not raw customer queries, quotes, model outputs or error strings.
  Unmeasured safety/determinism placeholders become null with `NOT_RUN`, not zero or 100%.
- Make entry points require `EVALUATION_OUTPUT_DIR`; missing configuration fails before a recipe.
  Updating these tools does not run providers, search infrastructure or model evaluation.

## Consequences and limits

This improves the reliability and safety of measuring retrieval; it does not improve the retriever,
prove a model gain, validate real customer Gold, or authorize release. New metrics cannot inherit a
v1 threshold, freeze, Test result or candidate identity. A future true-clause-Recall release gate
needs a newly versioned evaluation contract, independently justified threshold, same-identity Dev
comparison and separately authorized one-shot Test. No automatic migration/regrading is allowed.

The raw/MLX tools remain diagnostic, not complete operational safety evaluators; null checks need
dedicated observations before any pass claim. Hash-only observations are not anonymization and
remain owner-private. Removing source ICC metadata does not establish color-managed equivalence.
Real ClamAV/image HTTP qualification is separate from this task's synthetic tests.

No production DB/API/event contract changed, so no migration is needed. No GPU service, model,
route, PRIMARY, candidate matrix, frozen result or historical analysis run is modified.

## Related evidence

- ADR-0003, ADR-0010, ADR-0072, ADR-0084, ADR-0099, ADR-0103, ADR-0125, ADR-0126
- [Immediate mentoring improvements](../../../docs/engine/IMMEDIATE_MENTORING_IMPROVEMENTS_2026-09-09.md)
- [Policy Query Builder](../../../docs/rag/POLICY_QUERY_BUILDER_ARCHITECTURE.md)
