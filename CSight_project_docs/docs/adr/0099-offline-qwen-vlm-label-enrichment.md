# ADR-0099: Qwen VLM label enrichment is an offline derived dataset

- Status: Accepted
- Date: 2026-08-28

## Context

Kaputt has immutable official material, defect, severity and defect-type labels but no human-readable
product name or SKU. The pinned Qwen3.8 artifact has a vision encoder, while ADR-0012 deliberately
qualifies the Core-facing endpoint as text-only. CSight needs a research-only way to propose generic
product categories and visible descriptions without changing the canonical Vision or business-decision
contracts.

## Decision

- Keep the ADR-0012 endpoint and Core provider text-only. Run a separate, private, batch-only VLM
  endpoint with a different service name and port.
- Treat official Kaputt files and Parquet labels as read-only inputs. Store VLM output in a separate
  append-only JSONL artifact keyed by dataset revision, split, capture ID, image SHA-256, model
  revision, prompt version and schema version.
- The VLM may propose a generic product category, generic Korean display name, visible condition,
  visible defect candidates, location and evidence observations. It may not identify a real product,
  transcribe personal data, infer a market price, replace official labels or create a business action.
- Preserve official labels beside the derived output for later comparison. The verified material
  class may be supplied only to distinguish the primary item from its tray or cardboard packaging;
  defect, severity and defect-type labels remain hidden from the model prompt to avoid target-label
  leakage.
- Validate every provider response with a strict schema. Persist no raw prompt, raw response,
  reasoning, API key, absolute source path or image bytes.
- Send the cropped Query product as the first image and one deterministic cropped Reference for the
  same `item_identifier` as the second image. The prompt states the image roles, comparison rules,
  allowed generic metadata and prohibited inference. Record both image hashes and preprocessing
  manifests.
- Begin with a deterministic `plastic_hard` sample. Expansion requires human spot-checking and a
  recorded failure rate; VLM labels are never Human Gold.

## Consequences

- Product-name enrichment can be evaluated without changing E3, the canonical Vision schema, Case
  Resolution or Human Review.
- The full multimodal deployment has a separate memory and quality profile. A single RTX 4090 may
  fail to fit the vision encoder; an OOM is recorded as a failed qualification and must not silently
  fall back to the text-only endpoint.
- Kaputt remains restricted to the dataset terms for computer-vision education and scientific
  research. Derived artifacts retain provenance and cannot be presented as commercial customer data.
- A query image alone may not expose reference-relative anomalies. Full-batch enrichment is blocked
  until a human-reviewed paired-reference sample establishes useful product-type coverage and
  visible-evidence faithfulness.
- The first paired sample completed technically but found 0/2 official defect positives and useful
  product types in only 1/4 images. Qwen is therefore not a defect-label replacement; official labels
  and the qualified E3 path remain authoritative while paired Qwen output is optional derived data.
- Split product metadata from defect comparison. The product task may emit only a generic name,
  coarse category, form, generic use and visible evidence; its schema has no defect condition or
  business field. A 30-pair sample produced specific names for 25 records but exposed taxonomy
  mismatches, so it remains candidate data until human review and taxonomy approval.
