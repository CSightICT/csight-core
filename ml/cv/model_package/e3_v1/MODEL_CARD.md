# CSight E3 binary defect model card

## Intended use

This package versions the E3 DINOv2 ViT-S/14 binary any-defect classifier used by
the CSight proof of concept. It provides visual evidence for a customer-service
reviewer. It must not approve a refund, reject a customer claim, confirm that an
item is normal, or make any other final customer-service decision.

## Model and input

- Base model: `facebook/dinov2-small`
- Head: one-logit linear classifier over the CLS token
- Input: one RGB image, resized from the full frame to 1024 x 1024
- Output: sigmoid probability of the Kaputt `defect` label
- Selected checkpoint: E3 epoch 10, seed 42
- Checkpoint identity: see `manifest.json`; the checkpoint is not stored in Git

The resize intentionally preserves the full image content but not its aspect
ratio. This matches the E2/E3 validation and test preprocessing.

## Frozen operating point

The threshold `0.8984375` was selected on the validation split by maximizing
recall subject to precision of at least 0.90. A score at or above it means
`HIGH_CONFIDENCE_DEFECT_CANDIDATE`. A lower score means
`HUMAN_REVIEW_REQUIRED`; it is not confirmation that an item is normal.

At the frozen threshold, the held-out Kaputt test result was precision 0.954333,
recall 0.508422, specificity 0.988631, and F1 0.663411. Ranking metrics were AP
0.884863 and AUROC 0.931604. These results describe one public research dataset,
not live customer data or a commercial performance guarantee.

## Limitations

- The model only estimates whether any defect is present. It does not output a
  defect type, location, mask, severity, or policy decision.
- Its recall at the frozen high-precision threshold is about 51%, so low scores
  cannot be used to automatically clear cases.
- Kaputt does not represent Korean customer messages or every product, camera,
  lighting condition, and real customer environment.
- Training and selection used a single seed. Statistical variability was not
  measured.
- Restricted Kaputt data, checkpoint files, and predictions must remain outside
  Git and W&B artifacts and be handled under the dataset terms.

## Required safeguards

- A human makes the final decision in the CSight MVP.
- High-value, safety-sensitive, disputed, or otherwise high-risk cases are
  escalated regardless of model score.
- Run an actual-product domain-shift evaluation and Shadow Mode before any
  limited pilot.
- Preserve model, preprocess, threshold, and input hashes in the analysis record.

## Reproducibility

- W&B run ID: `e33m1xdx`
- Checkpoint SHA-256:
  `49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e`
- Package schema: `1.0`
- Preprocess version: `1.0`
- Threshold version: `1.0`
- Label version: `1.0`
