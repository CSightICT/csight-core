"""Create append-only Qwen VLM enrichment records for a deterministic Kaputt sample."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import io
import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DATASET_REVISION = "5305ccf4f661d84f19a83de35c782686d79f1c84"
MODEL_ARTIFACT = "cyankiwi/Qwen3.8-27B-AWQ-INT4"
MODEL_REVISION = "63768c10df38c0395e12ef49edac1bd539eaeeea"
SERVED_MODEL = "csight-qwen3.8-27b-vlm"
PROMPT_VERSION = "kaputt_paired_enrichment_2.0.1"
SCHEMA_VERSION = "kaputt_vlm_enrichment/2.0.0"
PRODUCT_PROMPT_VERSION = "kaputt_product_metadata_1.0.0"
PRODUCT_SCHEMA_VERSION = "kaputt_product_metadata/1.0.0"
MAX_SOURCE_BYTES = 20 * 1024 * 1024


class ProductCategory(str, Enum):  # noqa: UP042 - GPU node runs Python 3.10
    CONTAINER_OR_BOTTLE = "CONTAINER_OR_BOTTLE"
    KITCHEN_OR_DINING = "KITCHEN_OR_DINING"
    HOUSEHOLD_OR_STORAGE = "HOUSEHOLD_OR_STORAGE"
    PERSONAL_CARE = "PERSONAL_CARE"
    TOOL_OR_HARDWARE = "TOOL_OR_HARDWARE"
    TOY_OR_HOBBY = "TOY_OR_HOBBY"
    ELECTRONIC_ACCESSORY = "ELECTRONIC_ACCESSORY"
    OFFICE_OR_SCHOOL = "OFFICE_OR_SCHOOL"
    OTHER = "OTHER"
    UNCERTAIN = "UNCERTAIN"


class VisibleCondition(str, Enum):  # noqa: UP042 - GPU node runs Python 3.10
    NO_VISIBLE_DEFECT = "NO_VISIBLE_DEFECT"
    POSSIBLE_DEFECT = "POSSIBLE_DEFECT"
    VISIBLE_DEFECT = "VISIBLE_DEFECT"
    UNCERTAIN = "UNCERTAIN"


class VisibleDefectType(str, Enum):  # noqa: UP042 - GPU node runs Python 3.10
    ACTUATION = "actuation"
    DECONSTRUCTION = "deconstruction"
    DEFORMATION = "deformation"
    MISSING_UNIT = "missing_unit"
    PENETRATION = "penetration"
    SPILLAGE = "spillage"
    SUPERFICIAL = "superficial"
    OTHER = "other"


class VLMEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["kaputt_vlm_enrichment/2.0.0"]
    comparison_basis: Literal["QUERY_PLUS_REFERENCE"]
    reference_count: int = Field(ge=1, le=3)
    identity_specificity: Literal["GENERIC_ONLY"]
    product_category: ProductCategory
    generic_product_name_ko: str = Field(min_length=2, max_length=80)
    product_visual_summary_ko: str = Field(min_length=5, max_length=300)
    image_usable: bool
    image_usability_reason_ko: str = Field(min_length=2, max_length=160)
    visible_condition: VisibleCondition
    visible_defect_types: list[VisibleDefectType] = Field(max_length=7)
    visible_defect_summary_ko: str = Field(min_length=2, max_length=300)
    visible_defect_location_ko: str = Field(min_length=2, max_length=160)
    brand_or_personal_text_visible: bool
    evidence_observations_ko: list[str] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("visible_defect_types")
    @classmethod
    def deduplicate_visible_defect_types(
        cls, values: list[VisibleDefectType]
    ) -> list[VisibleDefectType]:
        return list(dict.fromkeys(values))


class ProductMetadataEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["kaputt_product_metadata/1.0.0"]
    observation_basis: Literal["QUERY_PLUS_REFERENCE"]
    reference_count: Literal[1]
    identity_specificity: Literal["GENERIC_ONLY"]
    product_category: ProductCategory
    generic_product_name_ko: str = Field(min_length=2, max_length=80)
    product_form_ko: str = Field(min_length=2, max_length=120)
    likely_generic_use_ko: str = Field(min_length=2, max_length=120)
    product_visual_summary_ko: str = Field(min_length=5, max_length=300)
    image_usable: bool
    image_usability_reason_ko: str = Field(min_length=2, max_length=160)
    brand_or_personal_text_visible: bool
    evidence_observations_ko: list[str] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)


SYSTEM_PROMPT = """You compare product images for a research-only visual defect dataset.
Return only the requested JSON. Describe only what is visibly supported by the image.
Use a generic Korean product name, never a brand, SKU, seller, exact product identity, person name,
barcode value, address, market price, refund amount, policy decision, or customer action.
Do not assume that an unclear image is normal. Use UNCERTAIN when evidence is insufficient.
Official defect labels are intentionally hidden. Your output is only a derived candidate label."""

USER_PROMPT = """The first image is the cropped Query product photo to assess. The second image is
a cropped Reference photo of the same item and is supplied only as its visual baseline. Compare the
item—not the cardboard or tray—across both photos. The dataset's canonical material class is
{material}; use that only to distinguish the primary item from packaging and never infer a defect
from it.

Give the most specific brand-neutral common product type supported by shape, visible parts, and
label context. You may use label context to infer a generic use, but never transcribe a brand,
barcode, QR code, or exact identity. Use '식별 불확실한 경질 플라스틱 제품' and category UNCERTAIN
only when even the generic type is unsupported. Set brand_or_personal_text_visible true when
printed brand-like text, a barcode, QR code, or personal text is visible, even if unreadable.

Assess only visible Query-versus-Reference differences. Do not treat viewpoint, lighting, scale,
item placement, or packaging arrangement as a defect. If the views do not support a reliable
comparison, use UNCERTAIN. Evidence observations must be short Korean comparative statements tied to
visible pixels. Do not repeat a defect type. Set comparison_basis to QUERY_PLUS_REFERENCE,
reference_count to 1, identity_specificity to GENERIC_ONLY, and schema_version to
kaputt_vlm_enrichment/2.0.0."""

PRODUCT_SYSTEM_PROMPT = """You create research-only generic product metadata from images.
Return only the requested JSON. Identify a common product type, form, and generic use only when
supported by visible shape, parts, or label context. Never return a brand, SKU, seller, exact
product identity, person name, barcode or QR value, address, price, refund amount, policy decision,
or customer action. Do not assess whether the item is defective. Your output is a derived candidate
for human review, not a ground-truth label."""

PRODUCT_USER_PROMPT = """The first image is a cropped Query product photo. The second image is a
cropped Reference photo of the same item. Use both views to produce brand-neutral product metadata
for the primary item, not the cardboard or tray. The canonical material class is {material}; use it
only as material context.

Choose the most specific common Korean product type visibly supported across either view. Shape,
functional parts, container form, and non-brand label context may support a generic type or use. Do
not use UNCERTAIN merely because viewpoints differ or the item may be damaged. Use the generic name
'식별 불확실한 경질 플라스틱 제품', category UNCERTAIN, and use '용도 식별 불가' only when neither
image supports a more useful common type or use. Do not transcribe visible text.

Do not compare defects and do not output a condition or business action. Set observation_basis to
QUERY_PLUS_REFERENCE, reference_count to 1, identity_specificity to GENERIC_ONLY, and schema_version
to kaputt_product_metadata/1.0.0. Evidence must be short Korean observations grounded in visible
shape, parts, or generic label context."""


def _normalize_defect_types(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value]
    else:
        parts = [item.strip() for item in str(value).split(",")]
    return sorted({item for item in parts if item})


def select_rows(
    rows: list[dict[str, Any]], *, material: str, limit: int, positive_fraction: float
) -> list[dict[str, Any]]:
    eligible = [row for row in rows if str(row.get("item_material", "")) == material]
    positives = sorted(
        (row for row in eligible if bool(row.get("defect"))),
        key=lambda row: str(row["capture_id"]),
    )
    negatives = sorted(
        (row for row in eligible if not bool(row.get("defect"))),
        key=lambda row: str(row["capture_id"]),
    )
    positive_count = min(len(positives), round(limit * positive_fraction))
    negative_count = min(len(negatives), limit - positive_count)
    selected = positives[:positive_count] + negatives[:negative_count]
    if len(selected) < limit:
        remainder = positives[positive_count:] + negatives[negative_count:]
        selected.extend(
            sorted(remainder, key=lambda row: str(row["capture_id"]))[: limit - len(selected)]
        )
    return sorted(selected, key=lambda row: str(row["capture_id"]))


def select_reference_rows(
    rows: list[dict[str, Any]], *, item_identifier: str, count: int
) -> list[dict[str, Any]]:
    matches = [row for row in rows if str(row.get("item_identifier", "")) == item_identifier]
    return sorted(
        matches,
        key=lambda row: (
            int(row.get("__index_level_0__", 0)),
            str(row.get("reference_crop", "")),
        ),
    )[:count]


def _load_rows(root: Path, split: str, *, kind: str) -> list[dict[str, Any]]:
    parquet: Any = importlib.import_module("pyarrow.parquet")

    table = parquet.read_table(root / f"{kind}-{split}.parquet")
    return table.to_pylist()


def _encode_image(image_path: Path) -> tuple[str, str, dict[str, Any]]:
    from PIL import Image

    source = image_path.read_bytes()
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError("SOURCE_IMAGE_TOO_LARGE")
    source_sha256 = hashlib.sha256(source).hexdigest()
    with Image.open(io.BytesIO(source)) as image:
        image = image.convert("RGB")
        original_size = image.size
        image.thumbnail((1024, 1024))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        encoded = output.getvalue()
        processed_size = image.size
    data_url = "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")
    preprocess = {
        "version": "kaputt_vlm_image_1.0.0",
        "original_size": list(original_size),
        "processed_size": list(processed_size),
        "format": "JPEG",
        "max_edge": 1024,
        "quality": 88,
    }
    return data_url, source_sha256, preprocess


def _request_enrichment(
    *,
    endpoint: str,
    api_key: str,
    query_data_url: str,
    reference_data_urls: list[str],
    material: str,
    timeout_seconds: float,
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    response_name: str,
) -> BaseModel:
    requests: Any = importlib.import_module("requests")

    payload = {
        "model": SERVED_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt.format(material=material)},
                    {"type": "image_url", "image_url": {"url": query_data_url}},
                    *[
                        {"type": "image_url", "image_url": {"url": reference_data_url}}
                        for reference_data_url in reference_data_urls
                    ],
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 900,
        "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": response_name,
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        },
    }
    response = requests.post(
        endpoint.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return response_model.model_validate_json(content)


def _task_contract(
    task: str,
) -> tuple[str, str, str, str, type[BaseModel], str]:
    if task == "product_metadata":
        return (
            PRODUCT_PROMPT_VERSION,
            PRODUCT_SCHEMA_VERSION,
            PRODUCT_SYSTEM_PROMPT,
            PRODUCT_USER_PROMPT,
            ProductMetadataEnrichment,
            "kaputt_product_metadata",
        )
    return (
        PROMPT_VERSION,
        SCHEMA_VERSION,
        SYSTEM_PROMPT,
        USER_PROMPT,
        VLMEnrichment,
        "kaputt_vlm_enrichment",
    )


def existing_success_keys(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    keys: set[str] = set()
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("status") == "SUCCEEDED":
                keys.add(str(record["idempotency_key"]))
    return keys


def _append_record(output_path: Path, record: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(args: argparse.Namespace) -> int:
    root = args.dataset_root.resolve()
    output_path = args.output.resolve()
    rows = _load_rows(root, args.split, kind="query")
    reference_rows = _load_rows(root, args.split, kind="reference")
    selected = select_rows(
        rows,
        material=args.material,
        limit=args.limit,
        positive_fraction=args.positive_fraction,
    )
    (
        prompt_version,
        schema_version,
        system_prompt,
        user_prompt,
        response_model,
        response_name,
    ) = _task_contract(args.task)
    if args.dry_run:
        print(
            json.dumps(
                {"selected": len(selected), "capture_ids": [r["capture_id"] for r in selected]}
            )
        )
        return 0
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise RuntimeError(f"{args.api_key_env} is required")
    existing = existing_success_keys(output_path)
    for row in selected:
        item_identifier = str(row["item_identifier"])
        references = select_reference_rows(
            reference_rows,
            item_identifier=item_identifier,
            count=1,
        )
        if len(references) != 1:
            raise RuntimeError("REFERENCE_METADATA_NOT_AVAILABLE")
        relative_path = Path(str(row["query_crop"] or ""))
        image_path = (root / relative_path).resolve()
        if root not in image_path.parents or not image_path.is_file():
            raise RuntimeError("SOURCE_IMAGE_PATH_INVALID")
        data_url, source_sha256, preprocess = _encode_image(image_path)
        encoded_references: list[tuple[Path, str, str, dict[str, Any]]] = []
        for reference in references:
            reference_relative_path = Path(str(reference["reference_crop"] or ""))
            reference_path = (root / reference_relative_path).resolve()
            if root not in reference_path.parents or not reference_path.is_file():
                raise RuntimeError("REFERENCE_IMAGE_PATH_INVALID")
            reference_data_url, reference_sha256, reference_preprocess = _encode_image(
                reference_path
            )
            encoded_references.append(
                (
                    reference_relative_path,
                    reference_data_url,
                    reference_sha256,
                    reference_preprocess,
                )
            )
        reference_digest = "|".join(item[2] for item in encoded_references)
        idempotency_key = hashlib.sha256(
            f"{DATASET_REVISION}|{args.split}|{row['capture_id']}|{source_sha256}|{reference_digest}|{MODEL_REVISION}|{prompt_version}".encode()
        ).hexdigest()
        if idempotency_key in existing:
            continue
        started = time.monotonic()
        base_record: dict[str, Any] = {
            "schema_version": schema_version,
            "idempotency_key": idempotency_key,
            "source": {
                "dataset": "amazon/kaputt",
                "dataset_revision": DATASET_REVISION,
                "split": args.split,
                "capture_id": str(row["capture_id"]),
                "item_identifier": item_identifier,
                "context_image_relative_path": Path(str(row["query_image"])).as_posix(),
                "query_crop_relative_path": relative_path.as_posix(),
                "query_crop_sha256": source_sha256,
                "official_labels": {
                    "item_material": str(row["item_material"]),
                    "defect": bool(row["defect"]),
                    "major_defect": bool(row["major_defect"]),
                    "defect_types": _normalize_defect_types(row["defect_types"]),
                },
                "reference_sources": [
                    {
                        "image_relative_path": item[0].as_posix(),
                        "image_sha256": item[2],
                        "preprocess": item[3],
                    }
                    for item in encoded_references
                ],
            },
            "provider": {
                "artifact": MODEL_ARTIFACT,
                "revision": MODEL_REVISION,
                "served_model": SERVED_MODEL,
                "prompt_version": prompt_version,
                "task": args.task,
                "preprocess": preprocess,
            },
        }
        try:
            enrichment = _request_enrichment(
                endpoint=args.endpoint,
                api_key=api_key,
                query_data_url=data_url,
                reference_data_urls=[item[1] for item in encoded_references],
                material=str(row["item_material"]),
                timeout_seconds=args.timeout_seconds,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                response_name=response_name,
            )
            base_record.update(
                {
                    "status": "SUCCEEDED",
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "enrichment": enrichment.model_dump(mode="json"),
                }
            )
        except Exception as exc:
            base_record.update(
                {
                    "status": "FAILED",
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "failure_code": type(exc).__name__,
                }
            )
        _append_record(output_path, base_record)
        if base_record["status"] == "SUCCEEDED":
            existing.add(idempotency_key)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--material", default="plastic_hard")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--positive-fraction", type=float, default=0.5)
    parser.add_argument(
        "--task",
        choices=("paired_defect", "product_metadata"),
        default="paired_defect",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18001/v1")
    parser.add_argument("--api-key-env", default="LLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not 0.0 <= args.positive_fraction <= 1.0:
        parser.error("--positive-fraction must be between 0 and 1")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
