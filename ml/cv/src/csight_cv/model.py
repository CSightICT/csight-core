from __future__ import annotations

import torch
from torch import nn
from transformers import Dinov2Model


class Dinov2BinaryClassifier(nn.Module):
    def __init__(
        self,
        model_name: str,
        mode: str,
        gradient_checkpointing: bool,
    ) -> None:
        super().__init__()
        if mode not in {"linear_probe", "full_finetune"}:
            raise ValueError(f"Unsupported training mode: {mode}")
        self.backbone = Dinov2Model.from_pretrained(model_name)
        hidden_size = int(self.backbone.config.hidden_size)
        self.classifier = nn.Linear(hidden_size, 1)
        if mode == "linear_probe":
            self.backbone.requires_grad_(False)
        elif gradient_checkpointing:
            self.backbone.gradient_checkpointing_enable()

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        output = self.backbone(pixel_values=pixel_values)
        cls_token = output.last_hidden_state[:, 0]
        return self.classifier(cls_token).squeeze(-1)

