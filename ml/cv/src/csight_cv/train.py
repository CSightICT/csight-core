from __future__ import annotations

import argparse
import json
import math
import random
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import wandb
import yaml
from torch import nn
from torch.optim import Adam
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

from csight_cv.data import KaputtQueryDataset
from csight_cv.metrics import binary_metrics
from csight_cv.model import Dinov2BinaryClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("linear_probe", "full_finetune"), required=True
    )
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--image-size", type=int)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-val-samples", type=int)
    parser.add_argument(
        "--wandb-mode", choices=("online", "offline", "disabled"), default="online"
    )
    parser.add_argument("--resume", type=Path)
    return parser.parse_args()


def load_config(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if args.epochs is not None:
        config["epochs"] = args.epochs
    if args.image_size is not None:
        config["image_size"] = args.image_size
    config["training_mode"] = args.mode
    config["max_train_samples"] = args.max_train_samples
    config["max_val_samples"] = args.max_val_samples
    return config


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def worker_seed(worker_id: int) -> None:
    worker_seed_value = torch.initial_seed() % (2**32)
    np.random.seed(worker_seed_value)
    random.seed(worker_seed_value)


def build_loader(
    dataset: KaputtQueryDataset,
    batch_size: int,
    num_workers: int,
    shuffle: bool,
    seed: int,
) -> DataLoader[dict[str, Any]]:
    generator = torch.Generator()
    generator.manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True,
        persistent_workers=num_workers > 0,
        worker_init_fn=worker_seed,
        generator=generator,
    )


@torch.inference_mode()
def evaluate(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    device: torch.device,
    criterion: nn.Module,
    use_bf16: bool,
) -> tuple[float, dict[str, float]]:
    model.eval()
    losses: list[float] = []
    labels: list[float] = []
    major_labels: list[float] = []
    scores: list[float] = []
    autocast = (
        torch.autocast(device_type="cuda", dtype=torch.bfloat16)
        if use_bf16
        else nullcontext()
    )
    for batch in loader:
        pixels = batch["pixel_values"].to(device, non_blocking=True)
        targets = batch["label"].to(device, non_blocking=True)
        with autocast:
            logits = model(pixels)
            loss = criterion(logits, targets)
        losses.append(float(loss.item()))
        labels.extend(targets.cpu().tolist())
        major_labels.extend(batch["major_label"].tolist())
        scores.extend(torch.sigmoid(logits).float().cpu().tolist())
    return float(np.mean(losses)), binary_metrics(labels, major_labels, scores)


def save_checkpoint(
    path: Path,
    model: nn.Module,
    optimizer: Adam,
    scheduler: LambdaLR,
    epoch: int,
    global_step: int,
    best_ap: float,
    config: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "epoch": epoch,
            "global_step": global_step,
            "best_validation_ap_any": best_ap,
            "config": config,
        },
        path,
    )


def main() -> None:
    args = parse_args()
    config = load_config(args.config, args)
    seed = int(config["seed"])
    seed_everything(seed)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for this training run")
    device = torch.device("cuda")
    use_bf16 = config["mixed_precision"] == "bf16" and torch.cuda.is_bf16_supported()
    dataset_root = Path(config["dataset_root"])
    auto_augment = str(config["train_augmentation"]["auto_augment"])

    train_dataset = KaputtQueryDataset(
        dataset_root,
        "train",
        int(config["image_size"]),
        True,
        auto_augment,
        args.max_train_samples,
    )
    validation_dataset = KaputtQueryDataset(
        dataset_root,
        "validation",
        int(config["image_size"]),
        False,
        auto_augment,
        args.max_val_samples,
    )
    train_loader = build_loader(
        train_dataset,
        int(config["batch_size"]),
        int(config["num_workers"]),
        True,
        seed,
    )
    validation_loader = build_loader(
        validation_dataset,
        int(config["batch_size"]),
        int(config["num_workers"]),
        False,
        seed,
    )

    model = Dinov2BinaryClassifier(
        str(config["model_name"]),
        args.mode,
        bool(config["gradient_checkpointing"]),
    ).to(device)
    learning_rate = (
        float(config["linear_probe_learning_rate"])
        if args.mode == "linear_probe"
        else float(config["learning_rate"])
    )
    trainable_parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
    optimizer = Adam(
        trainable_parameters,
        lr=learning_rate,
        betas=(0.9, 0.999),
        weight_decay=float(config["weight_decay"]),
    )
    accumulation = int(config["gradient_accumulation_steps"])
    total_updates = math.ceil(len(train_loader) / accumulation) * int(config["epochs"])
    scheduler = LambdaLR(
        optimizer,
        lr_lambda=lambda step: (
            0.5 * (1.0 + math.cos(math.pi * min(step, total_updates) / total_updates))
        ),
    )
    criterion = nn.BCEWithLogitsLoss()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_directory = Path(config["output_root"]) / f"{config['run_name']}-{timestamp}"
    run_directory.mkdir(parents=True, exist_ok=False)
    with (run_directory / "resolved-config.json").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)

    run = wandb.init(
        project=str(config["project_name"]),
        entity=config["wandb"].get("entity"),
        name=f"{config['run_name']}-{timestamp}",
        config=config,
        mode=args.wandb_mode,
        tags=list(config["wandb"].get("tags", [])) + [args.mode],
        job_type=args.mode,
        settings=wandb.Settings(start_method="thread"),
    )
    run.define_metric("train/global_step")
    run.define_metric("train/*", step_metric="train/global_step")
    run.define_metric("validation/epoch")
    run.define_metric("validation/*", step_metric="validation/epoch")

    start_epoch = 0
    global_step = 0
    best_ap = -1.0
    if args.resume is not None:
        checkpoint = torch.load(args.resume, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = int(checkpoint["epoch"]) + 1
        global_step = int(checkpoint["global_step"])
        best_ap = float(checkpoint["best_validation_ap_any"])

    no_improvement = 0
    autocast = (
        torch.autocast(device_type="cuda", dtype=torch.bfloat16)
        if use_bf16
        else nullcontext()
    )
    for epoch in range(start_epoch, int(config["epochs"])):
        model.train()
        if args.mode == "linear_probe":
            model.backbone.eval()
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        for batch_index, batch in enumerate(train_loader):
            pixels = batch["pixel_values"].to(device, non_blocking=True)
            targets = batch["label"].to(device, non_blocking=True)
            with autocast:
                logits = model(pixels)
                loss = criterion(logits, targets) / accumulation
            loss.backward()
            running_loss += float(loss.item()) * accumulation
            should_update = (
                batch_index + 1
            ) % accumulation == 0 or batch_index + 1 == len(train_loader)
            if should_update:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1
                if global_step % int(config["log_every_steps"]) == 0:
                    run.log(
                        {
                            "train/global_step": global_step,
                            "train/loss_step": float(loss.item()) * accumulation,
                            "train/learning_rate": optimizer.param_groups[0]["lr"],
                            "train/epoch_fraction": epoch
                            + (batch_index + 1) / len(train_loader),
                        }
                    )

        validation_loss, validation_metrics = evaluate(
            model, validation_loader, device, criterion, use_bf16
        )
        epoch_metrics = {
            "validation/epoch": epoch + 1,
            "train/loss_epoch": running_loss / len(train_loader),
            "validation/loss": validation_loss,
            **{f"validation/{key}": value for key, value in validation_metrics.items()},
        }
        run.log(epoch_metrics)
        improved = validation_metrics["ap_any"] > best_ap
        if improved:
            best_ap = validation_metrics["ap_any"]
            no_improvement = 0
            save_checkpoint(
                run_directory / "best.pt",
                model,
                optimizer,
                scheduler,
                epoch,
                global_step,
                best_ap,
                config,
            )
        else:
            no_improvement += 1
        save_checkpoint(
            run_directory / "last.pt",
            model,
            optimizer,
            scheduler,
            epoch,
            global_step,
            best_ap,
            config,
        )
        if no_improvement >= int(config["early_stopping_patience"]):
            break

    run.summary["best_validation_ap_any"] = best_ap
    run.summary["checkpoint_directory"] = str(run_directory)
    run.finish()


if __name__ == "__main__":
    main()

