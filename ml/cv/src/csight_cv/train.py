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
import yaml
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

import wandb
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
    checkpoint_group = parser.add_mutually_exclusive_group()
    checkpoint_group.add_argument("--resume", type=Path)
    checkpoint_group.add_argument("--init-checkpoint", type=Path)
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
    config["init_checkpoint"] = (
        str(args.init_checkpoint) if args.init_checkpoint is not None else None
    )
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


def build_optimizer(
    model: nn.Module,
    backbone_learning_rate: float,
    classifier_learning_rate: float,
    weight_decay: float,
    fused: bool = False,
) -> AdamW:
    groups: dict[str, dict[str, Any]] = {}
    for component in ("backbone", "classifier"):
        for decay_name, decay_value in (("decay", weight_decay), ("no_decay", 0.0)):
            group_name = f"{component}_{decay_name}"
            groups[group_name] = {
                "params": [],
                "lr": (
                    backbone_learning_rate
                    if component == "backbone"
                    else classifier_learning_rate
                ),
                "weight_decay": decay_value,
                "group_name": group_name,
            }

    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        component = "classifier" if name.startswith("classifier.") else "backbone"
        decay_name = (
            "decay" if parameter.ndim > 1 and not name.endswith(".bias") else "no_decay"
        )
        groups[f"{component}_{decay_name}"]["params"].append(parameter)

    parameter_groups = [group for group in groups.values() if group["params"]]
    return AdamW(parameter_groups, betas=(0.9, 0.999), fused=fused)


def cosine_with_warmup(
    step: int,
    total_updates: int,
    warmup_updates: int,
) -> float:
    if warmup_updates > 0 and step < warmup_updates:
        return float(step + 1) / float(warmup_updates)
    cosine_updates = max(1, total_updates - warmup_updates)
    progress = min(max(step - warmup_updates, 0) / cosine_updates, 1.0)
    return 0.5 * (1.0 + math.cos(math.pi * progress))


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
    optimizer: AdamW,
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
    torch.set_float32_matmul_precision(
        str(config.get("float32_matmul_precision", "high"))
    )
    torch.backends.cudnn.benchmark = bool(config.get("cudnn_benchmark", False))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for this training run")
    device = torch.device("cuda")
    use_bf16 = config["mixed_precision"] == "bf16" and torch.cuda.is_bf16_supported()
    dataset_root = Path(config["dataset_root"])
    auto_augment = str(config["train_augmentation"]["auto_augment"])
    resize_mode = str(
        config["train_augmentation"].get("resize_mode", "random_resized_crop")
    )
    horizontal_flip = float(config["train_augmentation"].get("horizontal_flip", 0.5))
    vertical_flip = float(config["train_augmentation"].get("vertical_flip", 0.5))

    train_dataset = KaputtQueryDataset(
        dataset_root,
        "train",
        int(config["image_size"]),
        True,
        auto_augment,
        args.max_train_samples,
        resize_mode=resize_mode,
        horizontal_flip=horizontal_flip,
        vertical_flip=vertical_flip,
    )
    validation_dataset = KaputtQueryDataset(
        dataset_root,
        "validation",
        int(config["image_size"]),
        False,
        auto_augment,
        args.max_val_samples,
        resize_mode="full_frame",
        horizontal_flip=0.0,
        vertical_flip=0.0,
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
    if args.init_checkpoint is not None:
        initialization_checkpoint = torch.load(
            args.init_checkpoint,
            map_location="cpu",
            weights_only=False,
        )
        model.load_state_dict(initialization_checkpoint["model_state_dict"])
    backbone_learning_rate = (
        float(config["linear_probe_learning_rate"])
        if args.mode == "linear_probe"
        else float(config["learning_rate"])
    )
    classifier_learning_rate = (
        float(config["linear_probe_learning_rate"])
        if args.mode == "linear_probe"
        else float(config.get("classifier_learning_rate", backbone_learning_rate))
    )
    optimizer = build_optimizer(
        model,
        backbone_learning_rate,
        classifier_learning_rate,
        float(config["weight_decay"]),
        bool(config.get("fused_optimizer", False)),
    )
    accumulation = int(config["gradient_accumulation_steps"])
    total_updates = math.ceil(len(train_loader) / accumulation) * int(config["epochs"])
    warmup_updates = int(total_updates * float(config.get("warmup_ratio", 0.0)))
    scheduler = LambdaLR(
        optimizer,
        lr_lambda=lambda step: cosine_with_warmup(step, total_updates, warmup_updates),
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
    )
    print(
        json.dumps(
            {
                "event": "run_started",
                "run_directory": str(run_directory),
                "training_mode": args.mode,
                "train_samples": len(train_dataset),
                "validation_samples": len(validation_dataset),
                "wandb_url": run.url,
                "init_checkpoint": (
                    str(args.init_checkpoint)
                    if args.init_checkpoint is not None
                    else None
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
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
                    learning_rates = {
                        str(group["group_name"]): float(group["lr"])
                        for group in optimizer.param_groups
                    }
                    run.log(
                        {
                            "train/global_step": global_step,
                            "train/loss_step": float(loss.item()) * accumulation,
                            "train/learning_rate": learning_rates.get(
                                "backbone_decay", learning_rates["classifier_decay"]
                            ),
                            "train/learning_rate_backbone": learning_rates.get(
                                "backbone_decay", 0.0
                            ),
                            "train/learning_rate_classifier": learning_rates[
                                "classifier_decay"
                            ],
                            "train/epoch_fraction": epoch
                            + (batch_index + 1) / len(train_loader),
                        }
                    )

        validation_loss, validation_metrics = evaluate(
            model, validation_loader, device, criterion, use_bf16
        )
        epoch_metrics = {
            "train/global_step": global_step,
            "validation/epoch": epoch + 1,
            "train/loss_epoch": running_loss / len(train_loader),
            "validation/loss": validation_loss,
            **{f"validation/{key}": value for key, value in validation_metrics.items()},
        }
        run.log(epoch_metrics)
        print(json.dumps(epoch_metrics, ensure_ascii=False), flush=True)
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
    print(
        json.dumps(
            {"event": "run_finished", "best_validation_ap_any": best_ap},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

