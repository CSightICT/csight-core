# ADR-0126: Diagnostic text/vision evidence alignment

- Status: Accepted
- Date: 2026-09-09
- Scope: offline, read-only replay of canonical results; no runtime activation

## Context

Extraction v2 reports customer claims while Vision reports either typed localized candidates or
one non-localizing any-defect assessment. There is no qualified claim-to-image matching stage.
Combining a customer claim with a high E3 score cannot establish the claim's type or location.
An empty detection list cannot contradict a claim. Image coordinates cannot establish product-relative
TOP/INSIDE/FRONT without an independently qualified orientation/part mapping.

## Decision

- Introduce an additive, pure diagnostic alignment contract and offline CLI. The input binds one
  tenant/run, extraction result/stage, exact source quotes, model/runtime/prompt identities, expected
  evidence snapshots and their Vision result identities. Foreign/duplicate/unsnapshotted results
  and digest mismatches fail closed before alignment. A missing image result stays visible.
- Preserve every claim separately by its original index. No claim text, quote, summary, image bytes,
  arbitrary attributes, provider response or URL is emitted. Output includes opaque references,
  source hashes and allowlisted versions only.
- Exact supported taxonomy matches above an explicitly supplied score threshold are
  `TYPE_CANDIDATE`, never verified factual support. The score is not probability. This initial
  mapping admits only DENT, CRACK, BREAKAGE and PACKAGING_DAMAGE; contamination, leakage, missing
  parts and wrong items need reference/semantic evidence not supplied by the current canonical
  contract. Functional failure cannot be established from one still image.
- USABLE quality with no explicit quality warning is required for a typed candidate. Unusable,
  not-evaluated quality, insufficient identity, image-level-only results, low scores, missing
  results and unsupported claim types produce `UNRESOLVED` with stable reason/request codes.
  Results whose quality is not evaluated are not retroactively declared usable.
- A matching type never verifies claim location or causal wording. No negative observation exists
  in the current contract, so there is intentionally no `CONTRADICTED` or `NORMAL` output.
  Other detected types are diagnostic observations, not counter-evidence.
- Reports are immutable files in new owner-only directories. Canonical input and profile hashes
  bind replay; source references and all relevant versions remain available. Schema is strict,
  bounded and rejects extra decision/approval fields. Advisory and human-review-required fields
  are fixed true. No DB, HTTP, Celery, route, policy, review or public API integration is added.
- A synthetic contract dataset exercises failure modes and replay only. It cannot prove text,
  vision or combined-model accuracy. Representative customer/commodity data and independently
  reviewed Gold, with grouped leakage checks, are prerequisites for those claims.

## Consequences

This closes the executable diagnostic matching gap without extending E3 capabilities or weakening
ADR-0072/0074/0096. No migration is needed because there is no persisted production schema change.
Deploying a future alignment stage requires an additive migration, authenticated ownership,
retention, immutable result/packet references, separate policy qualification and live workflow tests.
Model tuning, new visual detectors, spatial mappings and calibration require separate measured
experiments; none inherits qualification from the contract fixtures.

## Related decisions

- ADR-0003, ADR-0004, ADR-0010, ADR-0013–0017, ADR-0025
- ADR-0072, ADR-0074, ADR-0084, ADR-0096, ADR-0099, ADR-0103, ADR-0112, ADR-0123
