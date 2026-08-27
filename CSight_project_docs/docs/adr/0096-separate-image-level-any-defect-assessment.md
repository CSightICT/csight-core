# ADR-0096: Image-level any-defect assessment stays separate from detection

- Status: Accepted
- Date: 2026-08-27

## Context

The first DINOv2 E3 candidate is an image-level binary `defect` classifier. Its offline report
contains a validation-frozen high-precision threshold, but the model does not output defect type,
location, mask, or bounding box. Reusing the localized Detection contract would fabricate evidence;
interpreting a below-threshold score as normal would also contradict the reported recall limit.

## Decision

- Existing canonical Detection schema `1.0`, `vision_detections`, and native-to-canonical taxonomy
  mapping remain unchanged.
- A separate optional `VisionImageAssessment` represents `ANY_DEFECT` with the provider-returned
  `score`, provider-returned frozen `threshold`, fixed `GREATER_THAN_OR_EQUAL` comparison, and one
  of two Core-derived outcomes:
  - `HIGH_CONFIDENCE_DEFECT_CANDIDATE`
  - `BELOW_HIGH_CONFIDENCE_THRESHOLD`
- There is intentionally no `NORMAL` outcome. The second outcome requires human review or more
  evidence and cannot establish absence of a defect.
- An image-level assessment and localized detections cannot coexist in one canonical result. The
  binary remote contract requires an empty `detections` array and no defect-type field or geometry.
- The expected threshold is deployment configuration. Core compares it to the threshold returned
  by the provider and fails closed on drift. Core derives the outcome instead of trusting a remote
  boolean or label decision.
- The assessment is stored in one append-only, tenant-scoped child row per Vision Result. Provider,
  model, revision, dataset, taxonomy, threshold, preprocess, and postprocess versions remain on the
  immutable parent result.
- `binary_candidate` and `binary_below_threshold` Mock modes use deterministic synthetic scores and
  a threshold supplied explicitly by configuration. They are wiring scenarios, not E3 predictions
  or qualification evidence.
- Offline Kaputt report evidence, packaged checkpoint availability, live endpoint availability,
  and product-domain qualification are separate states. An offline report does not make Mock output
  production-qualified and does not prove performance on a selected PoC product.

## Consequences

CSight can demonstrate the complete asynchronous Vision path before the E3 checkpoint service is
available without inventing a defect type or location. A real E3 service can later replace the Mock
through the same port, but Limited PoC qualification still requires the packaged artifact, endpoint
contract test, and product-domain evaluation. Policy remains qualification-aware and Human Review
continues to own the final decision.
