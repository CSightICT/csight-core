from __future__ import annotations

import pytest
import torch
from csight_cv.data import build_transform
from csight_cv.train import build_optimizer, cosine_with_warmup
from torch import nn
from torchvision import transforms


class TinyModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.backbone = nn.Sequential(nn.Linear(4, 4), nn.LayerNorm(4))
        self.classifier = nn.Linear(4, 1)


def test_full_frame_transform_does_not_randomly_crop() -> None:
    transform = build_transform(
        1024,
        True,
        "rand-m9-mstd0.5-inc1",
        resize_mode="full_frame",
    )
    assert isinstance(transform.transforms[0], transforms.Resize)
    assert not any(
        isinstance(operation, transforms.RandomResizedCrop)
        for operation in transform.transforms
    )


def test_optimizer_separates_learning_rates_and_decay() -> None:
    optimizer = build_optimizer(TinyModel(), 5e-6, 1e-4, 0.05)
    groups = {group["group_name"]: group for group in optimizer.param_groups}
    assert groups["backbone_decay"]["lr"] == pytest.approx(5e-6)
    assert groups["classifier_decay"]["lr"] == pytest.approx(1e-4)
    assert groups["backbone_no_decay"]["weight_decay"] == 0.0
    assert groups["classifier_no_decay"]["weight_decay"] == 0.0


def test_optimizer_can_use_fused_cuda_path_when_requested() -> None:
    if not torch.cuda.is_available():
        pytest.skip("CUDA is required for fused AdamW")
    model = TinyModel().cuda()
    optimizer = build_optimizer(model, 2e-6, 3e-5, 0.05, fused=True)
    assert all(group["fused"] for group in optimizer.param_groups)


def test_cosine_scheduler_warms_up_then_decays() -> None:
    assert cosine_with_warmup(0, 100, 10) == pytest.approx(0.1)
    assert cosine_with_warmup(9, 100, 10) == pytest.approx(1.0)
    assert cosine_with_warmup(100, 100, 10) == pytest.approx(0.0)

