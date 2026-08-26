# CSight CV — Kaputt DINOv2 training

This directory contains the standalone research training pipeline for CSight's
Kaputt binary defect classifier. The model produces visual evidence; it does not
make the final customer-service decision.

## Scope

- Base model: `facebook/dinov2-small` (ViT-S/14)
- Input: full Kaputt query/tray image
- Target: `defect` binary label
- Secondary evaluation label: `major_defect`
- Tracking: Weights & Biases (W&B)
- Dataset/checkpoints: local only; never committed or uploaded as W&B artifacts

Kaputt is restricted to education and scientific computer-vision research under
its dataset terms. This pipeline is a non-commercial proof of concept.

## Environment

```bash
python3 -m venv --system-site-packages /home/data/venvs/csight-cv
source /home/data/venvs/csight-cv/bin/activate
python -m pip install -r ml/cv/requirements.txt
wandb login
```

Do not put `WANDB_API_KEY` or Hugging Face credentials in Git, logs, issues, or
configuration files.

## Data validation

```bash
python -m csight_cv.validate_data \
  --dataset-root /home/data/datasets/kaputt/extracted \
  --check-images
```

## Smoke run

```bash
PYTHONPATH=ml/cv/src python -m csight_cv.train \
  --config ml/cv/configs/kaputt_dinov2_vits14.yaml \
  --mode linear_probe \
  --max-train-samples 256 \
  --max-val-samples 128 \
  --epochs 1 \
  --wandb-mode online
```

## Full training

```bash
PYTHONPATH=ml/cv/src python -m csight_cv.train \
  --config ml/cv/configs/kaputt_dinov2_vits14.yaml \
  --mode full_finetune \
  --wandb-mode online
```

The official test split must only be evaluated after the model and threshold are
frozen:

```bash
PYTHONPATH=ml/cv/src python -m csight_cv.evaluate \
  --config ml/cv/configs/kaputt_dinov2_vits14.yaml \
  --checkpoint /home/data/csight-cv-runs/<run>/best.pt \
  --split test \
  --allow-test
```

## Logged W&B metrics

- `train/loss_step`, `train/loss_epoch`, `train/learning_rate`
- `validation/loss`, `validation/ap_any`, `validation/ap_major`
- `validation/auroc`, `validation/recall_at_50_precision`
- `validation/recall_at_1_fpr`
- GPU utilization, memory, CPU and system metrics from the W&B client

Only configuration and scalar metrics are sent to W&B. Kaputt images and model
checkpoints remain on the workstation.

