"""Versioned closed-set selection contract for the internal CSight PoC.

This module does not classify images.  It validates a human-approved allowlist and
applies a conservative demo-admission margin to an already persisted E3 score.
"""

from __future__ import annotations

import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

POC_CLOSED_SET_SCHEMA_VERSION = "poc_closed_set/1.0.0"
POC_CLOSED_SET_EXPANSION_SCHEMA_VERSION = "poc_closed_set/2.0.0"
POC_E3_RUNTIME_THRESHOLD = 0.8984375
POC_DEFECT_ADMISSION_MIN_SCORE = 0.95
POC_REFERENCE_ADMISSION_MAX_SCORE = 0.10

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PocClosedSetError(ValueError):
    """Raised when the committed PoC selection contract fails closed."""


class ProductClass(StrEnum):
    PERSONAL_CARE_CONTAINER = "PERSONAL_CARE_CONTAINER"
    FOOD_OR_SUPPLEMENT_CONTAINER = "FOOD_OR_SUPPLEMENT_CONTAINER"
    HOUSEHOLD_CHEMICAL_CONTAINER = "HOUSEHOLD_CHEMICAL_CONTAINER"
    KITCHEN_OR_STORAGE_ITEM = "KITCHEN_OR_STORAGE_ITEM"


class DefectGroup(StrEnum):
    OPENED_OR_DISASSEMBLED = "OPENED_OR_DISASSEMBLED"
    SHAPE_OR_STRUCTURAL_DAMAGE = "SHAPE_OR_STRUCTURAL_DAMAGE"
    SURFACE_DAMAGE_OR_LEAKAGE = "SURFACE_DAMAGE_OR_LEAKAGE"


class PocSourceKind(StrEnum):
    TOP100_SELECTED_CORRECT_DEFECT = "TOP100_SELECTED_CORRECT_DEFECT"
    USER_SUPPLIED_NORMAL_REFERENCE = "USER_SUPPLIED_NORMAL_REFERENCE"


NATIVE_DEFECT_TO_GROUP: dict[str, DefectGroup] = {
    "actuation": DefectGroup.OPENED_OR_DISASSEMBLED,
    "deconstruction": DefectGroup.OPENED_OR_DISASSEMBLED,
    "deformation": DefectGroup.SHAPE_OR_STRUCTURAL_DAMAGE,
    "penetration": DefectGroup.SHAPE_OR_STRUCTURAL_DAMAGE,
    "superficial": DefectGroup.SURFACE_DAMAGE_OR_LEAKAGE,
    "spillage": DefectGroup.SURFACE_DAMAGE_OR_LEAKAGE,
}


class ClosedSetClassDefinition(BaseModel):
    model_config = _MODEL_CONFIG

    code: str = Field(min_length=2, max_length=80)
    label_ko: str = Field(min_length=2, max_length=80)


class ClosedSetAssignment(BaseModel):
    model_config = _MODEL_CONFIG

    demo_id: str = Field(min_length=2, max_length=100)
    product_ref: str = Field(min_length=2, max_length=200)
    source_kind: PocSourceKind
    source_rank: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    product_class: ProductClass
    product_class_basis: Literal["HUMAN_APPROVED_SYNTHETIC_CATALOG"]
    source_defect_labels: tuple[str, ...]
    defect_groups: tuple[DefectGroup, ...]
    defect_group_basis: Literal[
        "KAPUTT_SOURCE_ANNOTATION_NOT_E3_PREDICTION",
        "NO_DEFECT_GROUP_LOW_SCORE_REFERENCE",
    ]
    human_approved: Literal[True]

    @model_validator(mode="after")
    def require_source_specific_assignment(self) -> Self:
        if len(set(self.source_defect_labels)) != len(self.source_defect_labels):
            raise ValueError("source defect labels must be unique")
        if len(set(self.defect_groups)) != len(self.defect_groups):
            raise ValueError("defect groups must be unique")
        if self.source_kind is PocSourceKind.TOP100_SELECTED_CORRECT_DEFECT:
            if not self.source_defect_labels or not self.defect_groups:
                raise ValueError("defect candidates require source labels and mapped groups")
            if self.defect_group_basis != "KAPUTT_SOURCE_ANNOTATION_NOT_E3_PREDICTION":
                raise ValueError("defect candidate group basis is invalid")
            unsupported = set(self.source_defect_labels) - set(NATIVE_DEFECT_TO_GROUP)
            if unsupported:
                raise ValueError("source defect labels include an unsupported PoC label")
            expected_groups = tuple(
                group
                for group in DefectGroup
                if group in {NATIVE_DEFECT_TO_GROUP[label] for label in self.source_defect_labels}
            )
            if self.defect_groups != expected_groups:
                raise ValueError("defect groups do not match source annotation mapping")
        else:
            if self.source_defect_labels or self.defect_groups:
                raise ValueError("low-score references cannot be assigned a defect group")
            if self.defect_group_basis != "NO_DEFECT_GROUP_LOW_SCORE_REFERENCE":
                raise ValueError("reference group basis is invalid")
        return self


class PocClosedSetRegistry(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["poc_closed_set/1.0.0", "poc_closed_set/2.0.0"]
    dataset_id: Literal["realistic-internal-demo-v2", "realistic-internal-demo-v3"]
    e3_runtime_threshold: float = Field(ge=0.0, le=1.0)
    defect_admission_min_score: float = Field(ge=0.0, le=1.0)
    reference_admission_max_score: float = Field(ge=0.0, le=1.0)
    gray_zone_disposition: Literal["EXCLUDE_FROM_CURATED_POC_OR_ROUTE_TO_HUMAN_REVIEW"]
    below_threshold_means_normal: Literal[False]
    e3_predicts_defect_type: Literal[False]
    qwen_product_role: Literal["CANDIDATE_ONLY_HUMAN_APPROVAL_REQUIRED"]
    product_classes: tuple[ClosedSetClassDefinition, ...]
    defect_groups: tuple[ClosedSetClassDefinition, ...]
    assignments: tuple[ClosedSetAssignment, ...]

    @model_validator(mode="after")
    def require_frozen_registry(self) -> Self:
        expected_dataset = (
            "realistic-internal-demo-v2"
            if self.schema_version == POC_CLOSED_SET_SCHEMA_VERSION
            else "realistic-internal-demo-v3"
        )
        if self.dataset_id != expected_dataset:
            raise ValueError("closed-set schema and dataset version do not match")
        if (
            self.e3_runtime_threshold != POC_E3_RUNTIME_THRESHOLD
            or self.defect_admission_min_score != POC_DEFECT_ADMISSION_MIN_SCORE
            or self.reference_admission_max_score != POC_REFERENCE_ADMISSION_MAX_SCORE
        ):
            raise ValueError("closed-set score gates drifted")
        expected_product_codes = tuple(item.value for item in ProductClass)
        expected_defect_codes = tuple(item.value for item in DefectGroup)
        if tuple(item.code for item in self.product_classes) != expected_product_codes:
            raise ValueError("product class registry drifted")
        if tuple(item.code for item in self.defect_groups) != expected_defect_codes:
            raise ValueError("defect group registry drifted")
        if len(self.assignments) != 10:
            raise ValueError("each closed-set pack requires a frozen ten-image allowlist")
        for field_name in ("demo_id", "product_ref", "image_sha256"):
            values = [getattr(item, field_name) for item in self.assignments]
            if len(values) != len(set(values)):
                raise ValueError(f"closed-set assignments duplicate {field_name}")
        return self


class PocAdmissionResult(BaseModel):
    model_config = _MODEL_CONFIG

    admitted: Literal[True]
    tier: Literal["CURATED_DEFECT_CANDIDATE", "HUMAN_CONFIRMED_LOW_SCORE_REFERENCE"]
    score: float = Field(ge=0.0, le=1.0)
    gate_version: Literal["poc_closed_set/1.0.0", "poc_closed_set/2.0.0"]


def load_poc_closed_set_registry(path: Path) -> PocClosedSetRegistry:
    if path.is_symlink() or not path.is_file():
        raise PocClosedSetError("PoC closed-set registry must be a regular non-symlink file")
    try:
        return PocClosedSetRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as error:
        raise PocClosedSetError("PoC closed-set registry failed validation") from error


def assess_poc_admission(
    assignment: ClosedSetAssignment,
    *,
    score: float,
    outcome: str,
    gate_version: Literal[
        "poc_closed_set/1.0.0", "poc_closed_set/2.0.0"
    ] = POC_CLOSED_SET_SCHEMA_VERSION,
) -> PocAdmissionResult:
    if isinstance(score, bool) or not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise PocClosedSetError("E3 admission score must be finite and within [0, 1]")
    if assignment.source_kind is PocSourceKind.TOP100_SELECTED_CORRECT_DEFECT:
        if outcome != "HIGH_CONFIDENCE_DEFECT_CANDIDATE":
            raise PocClosedSetError("defect allowlist item did not produce the expected E3 outcome")
        if score < POC_DEFECT_ADMISSION_MIN_SCORE:
            raise PocClosedSetError("defect candidate fell below the curated PoC score margin")
        return PocAdmissionResult(
            admitted=True,
            tier="CURATED_DEFECT_CANDIDATE",
            score=score,
            gate_version=gate_version,
        )
    if outcome != "BELOW_HIGH_CONFIDENCE_THRESHOLD":
        raise PocClosedSetError("reference allowlist item did not produce the expected E3 outcome")
    if score > POC_REFERENCE_ADMISSION_MAX_SCORE:
        raise PocClosedSetError("reference item entered the closed-set gray zone")
    return PocAdmissionResult(
        admitted=True,
        tier="HUMAN_CONFIRMED_LOW_SCORE_REFERENCE",
        score=score,
        gate_version=gate_version,
    )
