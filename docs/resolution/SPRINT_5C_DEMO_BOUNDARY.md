# Sprint 5C Demo Boundary and Limited PoC Promotion Gate

- Status: Accepted scope and evidence contract
- Date: 2026-08-27
- Current verdict: `SYNTHETIC_MOCK_SIMULATION_DEMO`

The current verdict remains a synthetic-data and Mock-Vision simulation demo until every promotion
gate in this document has machine-verifiable evidence. Implementation of a screen, API, or
successful `DRY_RUN` alone does not qualify the system as a Limited PoC.

## Internal demo boundary

The internal demo may use synthetic policy, synthetic Cases, Local-PoC LLM outputs, and Mock Vision.
It must label each qualification scope visibly and must not claim real-world performance, legal or
policy correctness, cost savings, or ROI.

The default evidence path remains:

```text
RAW query + HYBRID retrieval + reranker off + Top-3 citation
```

The Reranker and LLM Query Builder remain disabled until a new, sealed evaluation demonstrates an
improvement on the intended distribution.

## Required internal scenarios

| Scenario | Required observation |
|---|---|
| Complete Repair with `quantity`, or Refund with `amount` and `currency` | Authenticated Human Decision, one immutable Intent, one `DRY_RUN` Result, final Resolution `ACTION_DRY_RUN_VALIDATED`, side effects 0 |
| Refund missing `amount` or `currency` | `ACTION_NEEDS_INPUT`; Intent, adapter command, Attempt, and Result counts all 0 |
| Insufficient image evidence | Review action requests evidence; Human Decision, External Action Intent, Attempt, and Result counts all 0 |
| Safety Case | Reviewer claim/resolve is blocked; Admin may claim and Resolve with an audited Human Decision |
| Vision timeout | Analysis is Partial Success and routes to Human Review; automated Human Decision, Intent, Attempt, and Result counts all 0 |

Every scenario must also demonstrate same-tenant identity linkage, duplicate-delivery no-op behavior,
Packet/Decision/Intent/Result hash checks where applicable, ordered Events, and `cases.status`
unchanged by Resolution.

## Weeks 5–6 evidence inputs

Collection and approval begin in Week 1. Promotion evaluation in Weeks 5–6 requires all of the
following real-scope inputs:

- an identified customer candidate, one product category, and two or three defect types;
- at least 30 de-identified real Cases with counselor or domain-expert Gold decisions;
- real company policy with version and effective date;
- approved retention, deletion, EXIF-removal, and access-control handling;
- a real Vision manifest covering model, dataset, taxonomy, threshold, preprocessing, and
  postprocessing, plus defect-level evaluation; and
- reevaluation of Qwen3.8 Extraction and Grounding on the intended real distribution.

Absence of any input is a failed promotion gate, not a reason to substitute synthetic evidence.

## Limited PoC promotion gates

Every machine-gate check requires a non-empty evidence reference and must pass:

| Gate key | Pass condition |
|---|---|
| `customer_product_defect_scope` | Customer candidate confirmed, one product category, and 2–3 unique defect types |
| `deidentified_real_cases_and_gold` | De-identified Case count and Gold-reviewed count are each at least 30 |
| `versioned_effective_real_policy` | Actual company policy, version, and effective dates are present |
| `privacy_retention_exif_access_approval` | Retention, deletion, EXIF removal, and access control are all approved |
| `vision_qualification_or_explicit_exclusion` | Vision is qualified with a complete manifest and per-defect evaluation, or explicitly excluded with documented scope |
| `qwen_extraction_and_grounding_re_evaluated` | Extraction and Grounding are each `QUALIFIED` or `QUALIFIED_WITH_LIMITATIONS` on the intended distribution |
| `real_policy_case_query_distribution_evaluated` | Real policy, Case, and user-query distributions are all evaluated |
| `shadow_mode_human_comparison` | Shadow comparison is complete, Human Gold exists, and comparable Decision count is greater than zero |
| `zero_safety_violations` | Cross-tenant, unauthorized Decision, duplicate Intent/Result, `LIVE` execution, parameter inference, premature closure, and Decision mutation counts are exact integer zero |
| `backend_frontend_clean_environment_regression` | Backend, frontend, and clean-environment demo results are all exactly `PASS` |

There is no partial promotion. A missing, stale, unverifiable, or mismatched artifact makes its gate
fail.

## Machine-verifiable artifact expectations

The executable gate is `scripts/verify_poc_readiness.py`; the deliberately unqualified current
manifest is `evaluation/poc_readiness/current_gate.json`. `make verify-poc-readiness` reports the
current verdict, while `make require-limited-poc` exits unsuccessfully until every evidenced check
passes.

Additional promotion artifacts may be stored in the project-approved evaluation location, but each
must be immutable or sealed and addressable by a stable ID and SHA-256. Every envelope includes an artifact type and
schema version, artifact ID, release Git SHA, UTC generation time, generator version, input artifact
IDs and hashes, its own SHA-256, and a sealed flag. This document defines expectations only; it does
not fabricate external evidence or change the current manifest to passing.

| Artifact class | Minimum machine-verifiable fields |
|---|---|
| Scope manifest | schema version, customer-scope pseudonym, product category, defect taxonomy and versions |
| Real-Case dataset manifest | dataset ID/version/hash, de-identified Case count, split IDs/hashes, Gold source role, creation time |
| User-query distribution manifest | dataset ID/version/hash, de-identified query count, source scope, split IDs/hashes, distribution summary |
| Policy manifest | document/version/hash, effective-from/to, organization scope, ingestion profile and index IDs |
| Privacy approval | approval ID/version, dataset ID/hash, retention/deletion/EXIF/access decisions, approver role, effective time |
| Vision qualification | model/revision, dataset/taxonomy hashes, threshold and pre/postprocess versions, per-defect numerators/denominators and sample counts |
| Vision exclusion record, if used | approval ID/version, excluded flows and claims, dependent UI/API behavior, approver role, effective time |
| LLM reevaluation | model/revision, prompt/schema versions, dataset hash, Extraction/Grounding numerators, denominators, sample counts, failure taxonomy |
| Shadow comparison | release ID, dataset hash, paired recommendation/human Decision IDs, comparable denominator, difference numerator, missing-pair count |
| Safety-gate report | each prohibited outcome name, exact count, evaluated row/event range, query or test artifact hash |
| Regression evidence | Git SHA, migration head, dependency lock hash, backend/frontend test artifact hashes, pass/fail/skip counts |
| Clean demo record | release ID, environment manifest hash, five scenario IDs, expected/actual terminal states and row counts, timestamps |

Every aggregate KPI must carry its numerator, denominator, and sample count. Review time uses summed
actual claim intervals rather than Case age. The recommendation-difference rate uses only comparable
decisions. Additional-evidence rate, missing-action-input rate, `DRY_RUN` success rate, and analysis
failure/partial-success rate must state exclusions and zero denominators explicitly.

## Verdict rule

The release verdict may change to `LIMITED_POC` only when one promotion record references every gate
artifact, verifies every hash and release identity, and records all ten checks as passing. Otherwise
the user-facing label remains:

> Synthetic-data and Mock-Vision-based simulation demo

Until promotion, performance and ROI must not be presented as actual PoC results or projected
savings. `DRY_RUN` is never evidence of a completed external business action.

## Related contracts

- [Case Resolution Architecture](CASE_RESOLUTION_ARCHITECTURE.md)
- [Case Resolution State Machine](CASE_RESOLUTION_STATE_MACHINE.md)
- [External Action Contract](EXTERNAL_ACTION_CONTRACT.md)
