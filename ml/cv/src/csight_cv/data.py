from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from PIL import Image
from timm.data import create_transform
from torch.utils.data import Dataset
from torchvision import transforms
from torchvision.transforms import InterpolationMode

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class KaputtSample:
    image_path: Path
    capture_id: str
    item_identifier: str
    defect: float
    major_defect: float
    item_material: str
    defect_types: str


def build_transform(image_size: int, training: bool, auto_augment: str) -> Any:
    if training:
        return create_transform(
            input_size=(3, image_size, image_size),
            is_training=True,
            interpolation="bicubic",
            mean=IMAGENET_MEAN,
            std=IMAGENET_STD,
            hflip=0.5,
            vflip=0.5,
            color_jitter=None,
            auto_augment=auto_augment,
            re_prob=0.0,
        )
    return transforms.Compose(
        [
            transforms.Resize(
                (image_size, image_size), interpolation=InterpolationMode.BICUBIC
            ),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


class KaputtQueryDataset(Dataset[dict[str, Any]]):
    def __init__(
        self,
        dataset_root: Path,
        split: str,
        image_size: int,
        training: bool,
        auto_augment: str,
        max_samples: int | None = None,
    ) -> None:
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"Unsupported split: {split}")
        self.dataset_root = dataset_root
        frame = pd.read_parquet(dataset_root / f"query-{split}.parquet")
        if max_samples is not None:
            frame = frame.iloc[:max_samples]
        self.frame = frame.reset_index(drop=True)
        self.transform = build_transform(image_size, training, auto_augment)

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.frame.iloc[index]
        image_path = self.dataset_root / str(row["query_image"])
        try:
            with Image.open(image_path) as image:
                pixel_values = self.transform(image.convert("RGB"))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load capture_id={row['capture_id']}"
            ) from exc
        return {
            "pixel_values": pixel_values,
            "label": torch.tensor(float(row["defect"]), dtype=torch.float32),
            "major_label": torch.tensor(
                float(row["major_defect"]), dtype=torch.float32
            ),
            "capture_id": str(row["capture_id"]),
            "item_identifier": str(row["item_identifier"]),
            "item_material": str(row["item_material"]),
            "defect_types": str(row["defect_types"]),
        }

