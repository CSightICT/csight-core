# Kaputt Qwen3.8 VLM Label Enrichment

## Scope

This is an offline research artifact, not a CSight online decision path. The immutable Kaputt labels
remain canonical. Qwen proposes only generic product metadata and visible observations for later human
review.

## Verified source snapshot

- Source root on the private GPU node: `/home/data/datasets/kaputt/extracted`
- Official query rows/images: train 85,326; validation 4,874; test 10,067; total 100,267
- `plastic_hard`: 10,095 rows; 1,323 official defect positives and 8,772 negatives
- The parent directory contains the official archives and license. It is not copied into Git.
- Dataset use remains limited to computer-vision education and scientific research under the Kaputt
  terms. No commercial customer-data claim is made.

## Output contract

`kaputt_vlm_enrichment/2.0.0` JSONL stores:

- dataset revision, split, capture ID, relative image path and SHA-256;
- immutable official material/defect/severity/type labels;
- pinned model/revision, prompt and preprocessing versions;
- validated generic category/name, visible-condition candidates, evidence observations and confidence;
- terminal `SUCCEEDED` or `FAILED`, latency and a non-sensitive failure code.

It never stores image bytes, absolute source paths, raw prompts/responses/reasoning, credentials,
transcribed personal or barcode text, inferred brand/SKU, price, refund amount or business decision.

## Runtime boundary

`infra/llm/compose.vlm.yml` uses the pinned Qwen3.8 artifact with its vision encoder on private port
18001. It is separate from the ADR-0012 text-only Core endpoint and uses a distinct served-model name.
No fallback occurs if the full VLM does not fit the single RTX 4090.

Begin with a deterministic balanced test sample. Expansion requires a human spot-check of product
category usefulness, unsupported-detail rate, official-label disagreement and schema-failure rate.

## 2026-08-28 query-only qualification sample

- The separate VLM loaded successfully on the single RTX 4090 and served four balanced
  `plastic_hard` test images without schema failure. Each request took about 9.3–10.8 seconds.
- Prompt `1.2.0` produced only `GENERIC_ONLY` identities, removed repeated defect types and had no
  email, phone, currency or long-number pattern in the structured output.
- Manual image inspection accepted the generic `사탕 용기` proposal for one image. Three other
  visibly recognizable forms—a mini-muffin tray, a body-care bottle and a glue bottle—remained
  `UNCERTAIN`, so useful product-type coverage was only 1/4 in this tiny sample.
- Both official defect-positive images were conservatively marked `UNCERTAIN`. Kaputt anomalies can
  be defined relative to an item's reference state, so this is not evidence that query-image-only
  Qwen can recover the official defect labels.
- Full 10,095-row enrichment is therefore not qualified. The next quality experiment must pair a
  human-reviewed sample with the corresponding reference image/crop and separately score product
  type usefulness and visible-evidence faithfulness. Official labels remain canonical.

The append-only sample is stored privately on the GPU node under
`/home/data/datasets/kaputt/derived/csight-qwen38/`; it is not copied into Git.

## Paired image contract

Prompt `2.0.1` no longer sends a Query image alone. Each request contains, in order:

1. a text prompt that identifies the first image as the Query and the second as the same item's
   visual Reference, defines allowed generic metadata, and forbids target-label leakage and business
   inference;
2. the selected Query product Crop;
3. one deterministic Reference product Crop for the same immutable `item_identifier`.

Both image hashes, relative paths and preprocessing manifests are stored in
`kaputt_vlm_enrichment/2.0.0`. The full tray image remains provenance context but is not sent to the
model. The private vLLM service allows exactly two images per request.

## 2026-08-28 paired qualification result

- Four Query Crops and four same-item Reference Crops were selectively extracted from the official
  archives; no full 31–42 GiB crop archive was expanded.
- Paired prompt `2.0.1` completed 4/4 with strict schema, `QUERY_PLUS_REFERENCE`, one Reference per
  record and no email, phone, currency or long-number pattern. Latency was 9.6–12.0 seconds per pair.
- Product-type usefulness remained 1/4 in manual review. The model described visible forms but kept
  the muffin tray, body-care bottle and glue bottle under `UNCERTAIN`.
- It detected neither of the two official defect-positive rows. This means the paired generic VLM is
  technically connected but is not qualified as a Kaputt defect labeler. Official labels and the E3
  vision model remain the defect sources; Qwen output remains optional metadata/evidence candidates.
- The paired result SHA-256 is
  `159f5ded7eb9559d5b322ca9d24d48cfc117ed4c94a922f89c7145cb8bac3811`.

## Product metadata task

The defect-comparison task and product-metadata task are separate provider contracts. Product
prompt `kaputt_product_metadata_1.0.0` still receives the Query Crop and same-item Reference Crop,
but its strict `kaputt_product_metadata/1.0.0` schema contains no condition, defect, price, refund,
brand, SKU or business-action field. It proposes only:

- brand-neutral Korean product name and coarse category;
- visible form and likely generic use;
- image usability, visible-text presence, evidence observations and confidence.

Official defect labels remain provenance outside the prompt and are not predicted by this task.

## 2026-08-28 product metadata sample 30

- The deterministic test sample contains 15 official defect-positive and 15 negative rows. This
  balance is only for source coverage; the product task never receives the target labels.
- Thirty Query Crops and 28 unique same-item Reference Crops were available. The official archives
  were scanned once each and only the missing selected files were extracted.
- Inference completed 30/30 with zero provider/schema failure. Latency was 7.4–10.0 seconds per pair,
  p50 8.5 seconds and p95 10.0 seconds.
- Twenty-five records proposed a specific generic name and five used the explicit uncertain name.
  This is an 83.3% specificity rate, not an accuracy score or Human Gold.
- All records were `GENERIC_ONLY` and paired; prohibited defect/business fields, email, phone,
  currency and long-number patterns were absent.
- Visual contact-sheet review found useful name candidates such as a muffin pan, body-lotion bottle,
  adhesive bottle and personal-care containers. It also found coarse-category mismatches because the
  current enum lacks dedicated supplement, cleaning/chemical and pet-care categories. Automatic
  catalog application is therefore blocked pending a human-reviewed taxonomy and labels.
- The private append-only result is
  `/home/data/datasets/kaputt/derived/csight-qwen38/plastic_hard_test_product30_prompt_1_0_0.jsonl`
  with SHA-256 `7ddc9197c957f9e81b5560476a789f06d555e346ff8dc0df734c076abfef846a`.
