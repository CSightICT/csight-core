# ADR-0100: Curated closed-set admission for the internal PoC

- Status: Accepted
- Date: 2026-08-28

## Context

The current internal demo uses six selected-correct Kaputt positives and four user-provided
low-score references. E3 is an image-level binary any-defect model and cannot identify a product,
defect type, location, or business action. Qwen VLM product metadata is structurally usable as a
candidate, but it has no Human Gold accuracy qualification and its defect-comparison experiment
failed the quality gate. Using either model to invent runtime product or defect classes would
overstate the evidence. Using only high-scoring examples without an explicit selection contract
would also hide selection bias.

## Decision

- Internal PoC dataset admission uses the versioned `poc_closed_set/1.0.0` registry.
- The configured product classes are:
  - `PERSONAL_CARE_CONTAINER`
  - `FOOD_OR_SUPPLEMENT_CONTAINER`
  - `HOUSEHOLD_CHEMICAL_CONTAINER`
  - `KITCHEN_OR_STORAGE_ITEM`
- Kaputt annotations are grouped for scenario metadata only:
  - `actuation`, `deconstruction` -> `OPENED_OR_DISASSEMBLED`
  - `deformation`, `penetration` -> `SHAPE_OR_STRUCTURAL_DAMAGE`
  - `superficial`, `spillage` -> `SURFACE_DAMAGE_OR_LEAKAGE`
- Product-class assignments require one human approval. Qwen may suggest a candidate but cannot
  admit a record or become the stored authority.
- Defect-group assignments come only from the frozen source annotation or later Human Gold. They
  are never derived from the E3 binary score.
- The E3 runtime threshold remains `0.8984375`. The closed-set PoC applies a separate selection
  margin: selected defect candidates require score `>= 0.95`; human-confirmed low-score references
  require score `<= 0.10`.
- Scores in `(0.10, 0.95)` are excluded from the curated demo or routed to Human Review. A score
  below the E3 threshold is never called normal.
- Registry identity, source SHA, source labels, E3 outcome, and selection margin fail closed before
  a seed report can claim admission.
- The closed-set output is a capability-demo dataset, not an accuracy or calibration evaluation.
  Human Review continues to own the final decision and external actions remain DRY-RUN only.

## Consequences

The current ten-image demo has deterministic, auditable admission rules and natural-language class
labels. It represents two of the four configured product classes; food/supplement and household
chemical images remain unrepresented and cannot be claimed as tested coverage. All three defect
groups appear through multi-label source annotations, but E3 still predicts only any-defect. MVP
expansion requires Human Gold and representative evaluation rather than lowering the curated-data
gate or promoting Qwen confidence to an authority.

The additive `poc_closed_set/2.0.0` registry and `realistic-internal-demo-v3` pack subsequently add
ten independently allowlisted images without mutating the original ten. The combined internal
demo now contains twelve defect candidates and eight human-confirmed low-score references and
represents all four configured product classes. Representation is not class accuracy, calibration,
or market-distribution coverage; those claims still require a separate Human Gold evaluation.
