#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${CSIGHT_CV_WORKDIR:-/home/data/csight-cv-work}"
DATASET_ROOT="${KAPUTT_DATASET_ROOT:-/home/data/datasets/kaputt/extracted}"
EXTRACT_PID_FILE="${KAPUTT_EXTRACT_PID_FILE:-/home/data/datasets/kaputt/query-image-extract.pid}"
TRAIN_PID_FILE="${CSIGHT_CV_TRAIN_PID_FILE:-/home/data/csight-cv-training.pid}"
TRAIN_LOG="${CSIGHT_CV_TRAIN_LOG:-/home/data/csight-cv-training.log}"
READY_LOG="${CSIGHT_CV_READY_LOG:-/home/data/csight-cv-ready.log}"
POLL_SECONDS="${CSIGHT_CV_POLL_SECONDS:-60}"

declare -A EXPECTED=(
  [train]=85326
  [validation]=4874
  [test]=10067
)

cd "$WORKDIR"
source /home/data/venvs/csight-cv/bin/activate

count_images() {
  local split="$1"
  local image_dir="$DATASET_ROOT/data/$split/query-data/image"
  if [[ ! -d "$image_dir" ]]; then
    printf '0\n'
    return
  fi
  find "$image_dir" -type f | wc -l
}

while true; do
  extract_running=false
  if [[ -s "$EXTRACT_PID_FILE" ]]; then
    extract_pid="$(<"$EXTRACT_PID_FILE")"
    if kill -0 "$extract_pid" 2>/dev/null; then
      extract_running=true
    fi
  fi

  ready=true
  status=()
  for split in train validation test; do
    count="$(count_images "$split")"
    status+=("$split=$count/${EXPECTED[$split]}")
    if [[ "$count" -ne "${EXPECTED[$split]}" ]]; then
      ready=false
    fi
  done
  printf '%s extraction_running=%s %s\n' \
    "$(date --iso-8601=seconds)" "$extract_running" "${status[*]}" | tee -a "$READY_LOG"

  if [[ "$ready" == true && "$extract_running" == false ]]; then
    break
  fi
  if [[ "$extract_running" == false ]]; then
    echo "Extraction stopped before all expected images were present." | tee -a "$READY_LOG"
    exit 1
  fi
  sleep "$POLL_SECONDS"
done

PYTHONPATH=ml/cv/src python -m csight_cv.validate_data \
  --dataset-root "$DATASET_ROOT" \
  --check-images | tee -a "$READY_LOG"

if [[ -s "$TRAIN_PID_FILE" ]]; then
  previous_pid="$(<"$TRAIN_PID_FILE")"
  if kill -0 "$previous_pid" 2>/dev/null; then
    echo "Training is already running with PID $previous_pid." | tee -a "$READY_LOG"
    exit 1
  fi
fi

nohup env PYTHONPATH=ml/cv/src python -m csight_cv.train \
  --config ml/cv/configs/kaputt_dinov2_vits14.yaml \
  --mode full_finetune \
  --wandb-mode online \
  >"$TRAIN_LOG" 2>&1 &
train_pid=$!
printf '%s\n' "$train_pid" >"$TRAIN_PID_FILE"
echo "Started full fine-tuning with PID $train_pid; log=$TRAIN_LOG" | tee -a "$READY_LOG"

