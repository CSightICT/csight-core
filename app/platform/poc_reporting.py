"""Technology-neutral immutable review report and PoC metric contracts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.case.models import JsonValue
from app.platform.errors import CSightError

REVIEW_REPORT_SCHEMA_VERSION = "review_report/1.0.0"
POC_SUMMARY_SCHEMA_VERSION = "poc_summary/1.0.0"
CUSTOMER_COMMUNICATION_SCHEMA_VERSION = "customer_communication_simulation/1.0.0"
DATA_ASSET_SCHEMA_VERSION = "case_learning_asset/1.0.0"
DATA_ASSET_BASELINE_MINIMUM = 30
DATA_ASSET_DRIFT_MINIMUM = 60


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReviewReportNotFoundError(CSightError):
    code = "REVIEW_REPORT_NOT_FOUND"
    default_message = "The requested immutable review report was not found."


class CustomerCommunicationNotAvailableError(CSightError):
    code = "CUSTOMER_COMMUNICATION_NOT_AVAILABLE"
    default_message = "A terminal review report is required before creating customer communication."


def canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ReviewReport(_Strict):
    schema_version: Literal["review_report/1.0.0"] = REVIEW_REPORT_SCHEMA_VERSION
    report_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    resolution_id: str = Field(min_length=1)
    resolution_version: int = Field(ge=1)
    terminal_event_id: str = Field(min_length=1)
    case_snapshot: dict[str, JsonValue]
    analysis_snapshot: dict[str, JsonValue]
    policy_snapshot: dict[str, JsonValue]
    review_snapshot: dict[str, JsonValue]
    resolution_snapshot: dict[str, JsonValue]
    dry_run_snapshot: dict[str, JsonValue]
    qualification_snapshot: dict[str, JsonValue]
    data_scope: dict[str, JsonValue]
    generated_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def verify_content_hash(self) -> ReviewReport:
        expected = canonical_json_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        if self.content_hash != expected:
            raise ValueError("review report content hash mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        report_id: str,
        tenant_id: str,
        case_id: str,
        resolution_id: str,
        resolution_version: int,
        terminal_event_id: str,
        case_snapshot: dict[str, JsonValue],
        analysis_snapshot: dict[str, JsonValue],
        policy_snapshot: dict[str, JsonValue],
        review_snapshot: dict[str, JsonValue],
        resolution_snapshot: dict[str, JsonValue],
        dry_run_snapshot: dict[str, JsonValue],
        qualification_snapshot: dict[str, JsonValue],
        data_scope: dict[str, JsonValue],
        generated_at: datetime,
    ) -> Self:
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        normalized_at = generated_at.astimezone(UTC)
        payload: dict[str, object] = {
            "schema_version": REVIEW_REPORT_SCHEMA_VERSION,
            "report_id": report_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resolution_id": resolution_id,
            "resolution_version": resolution_version,
            "terminal_event_id": terminal_event_id,
            "case_snapshot": case_snapshot,
            "analysis_snapshot": analysis_snapshot,
            "policy_snapshot": policy_snapshot,
            "review_snapshot": review_snapshot,
            "resolution_snapshot": resolution_snapshot,
            "dry_run_snapshot": dry_run_snapshot,
            "qualification_snapshot": qualification_snapshot,
            "data_scope": data_scope,
            "generated_at": normalized_at.isoformat().replace("+00:00", "Z"),
        }
        return cls(**payload, content_hash=canonical_json_hash(payload))  # pyright: ignore[reportArgumentType]


class CustomerCommunicationSimulation(_Strict):
    schema_version: Literal["customer_communication_simulation/1.0.0"] = (
        CUSTOMER_COMMUNICATION_SCHEMA_VERSION
    )
    communication_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    review_report_id: str = Field(min_length=1)
    channel: Literal["EMAIL"] = "EMAIL"
    template_name: Literal["customer_outcome_email"] = "customer_outcome_email"
    template_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    recipient_label: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=10000)
    delivery_status: Literal["SIMULATED_NOT_SENT"] = "SIMULATED_NOT_SENT"
    side_effects_performed: Literal[False] = False
    created_by: str = Field(min_length=1)
    created_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at")
    @classmethod
    def require_created_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def verify_hash(self) -> CustomerCommunicationSimulation:
        expected = canonical_json_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        if self.content_hash != expected:
            raise ValueError("customer communication content hash mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        created_at = values.get("created_at")
        if not isinstance(created_at, datetime) or created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        payload = {
            "schema_version": CUSTOMER_COMMUNICATION_SCHEMA_VERSION,
            **values,
            "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "channel": "EMAIL",
            "template_name": "customer_outcome_email",
            "template_version": "1.1.0",
            "delivery_status": "SIMULATED_NOT_SENT",
            "side_effects_performed": False,
        }
        return cls(**payload, content_hash=canonical_json_hash(payload))  # pyright: ignore[reportArgumentType]


class CaseLearningAsset(_Strict):
    schema_version: Literal["case_learning_asset/1.0.0"] = DATA_ASSET_SCHEMA_VERSION
    asset_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    review_report_id: str = Field(min_length=1)
    subject_pseudonym: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    feature_snapshot: dict[str, JsonValue]
    label_snapshot: dict[str, JsonValue]
    version_snapshot: dict[str, JsonValue]
    privacy_scope: dict[str, JsonValue]
    created_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at")
    @classmethod
    def require_asset_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def verify_hash(self) -> CaseLearningAsset:
        expected = canonical_json_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        if self.content_hash != expected:
            raise ValueError("case learning asset content hash mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        created_at = values.get("created_at")
        if not isinstance(created_at, datetime) or created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        payload = {
            "schema_version": DATA_ASSET_SCHEMA_VERSION,
            **values,
            "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
        return cls(**payload, content_hash=canonical_json_hash(payload))  # pyright: ignore[reportArgumentType]


class DataAssetSummary(_Strict):
    schema_version: Literal["case_learning_asset_summary/1.0.0"] = (
        "case_learning_asset_summary/1.0.0"
    )
    generated_at: datetime
    total_records: int = Field(ge=0)
    eligible_records: int = Field(default=0, ge=0)
    excluded_records: int = Field(default=0, ge=0)
    eligible_source_scope: Literal["PILOT_LIVE"] = "PILOT_LIVE"
    source_scope_distribution: dict[str, int] = Field(default_factory=dict)
    baseline_minimum: int = DATA_ASSET_BASELINE_MINIMUM
    drift_review_minimum: int = DATA_ASSET_DRIFT_MINIMUM
    readiness_status: Literal[
        "COLLECTING_BASELINE", "COLLECTING_COMPARISON", "READY_FOR_DRIFT_REVIEW"
    ]
    drift_evaluation_available: bool
    decision_distribution: dict[str, int]
    resolution_distribution: dict[str, int]
    product_distribution: dict[str, int]
    model_version_distribution: dict[str, int]
    policy_version_distribution: dict[str, int]
    recent_records: tuple[CaseLearningAsset, ...] = ()

    @field_validator("generated_at")
    @classmethod
    def require_summary_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(UTC)


class MetricUnit(StrEnum):
    RATIO = "ratio"
    SECONDS = "seconds"


class PocMetric(_Strict):
    numerator: float = Field(ge=0)
    denominator: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    value: float | None
    unit: MetricUnit

    @model_validator(mode="after")
    def validate_value(self) -> PocMetric:
        if not math.isfinite(self.numerator):
            raise ValueError("metric numerator must be finite")
        expected = None if self.denominator == 0 else self.numerator / self.denominator
        if expected is None:
            if self.value is not None:
                raise ValueError("zero-denominator metrics must expose null value")
        elif self.value is None or not math.isclose(self.value, expected, rel_tol=1e-12):
            raise ValueError("metric value must equal numerator divided by denominator")
        if self.unit is MetricUnit.RATIO and self.numerator > self.denominator:
            raise ValueError("ratio numerator cannot exceed denominator")
        return self

    @classmethod
    def from_fraction(
        cls,
        *,
        numerator: float,
        denominator: int,
        sample_count: int,
        unit: MetricUnit,
    ) -> Self:
        value = None if denominator == 0 else numerator / denominator
        return cls(
            numerator=numerator,
            denominator=denominator,
            sample_count=sample_count,
            value=value,
            unit=unit,
        )


class PocSummary(_Strict):
    schema_version: Literal["poc_summary/1.0.0"] = POC_SUMMARY_SCHEMA_VERSION
    generated_at: datetime
    eligible_source_scope: Literal["PILOT_LIVE"] = "PILOT_LIVE"
    eligible_case_count: int = Field(default=0, ge=0)
    excluded_case_count: int = Field(default=0, ge=0)
    review_time: PocMetric
    recommendation_difference_rate: PocMetric
    additional_evidence_request_rate: PocMetric
    action_input_missing_rate: PocMetric
    dry_run_success_rate: PocMetric
    analysis_failure_rate: PocMetric
    analysis_partial_success_rate: PocMetric

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "CUSTOMER_COMMUNICATION_SCHEMA_VERSION",
    "DATA_ASSET_BASELINE_MINIMUM",
    "DATA_ASSET_DRIFT_MINIMUM",
    "DATA_ASSET_SCHEMA_VERSION",
    "POC_SUMMARY_SCHEMA_VERSION",
    "REVIEW_REPORT_SCHEMA_VERSION",
    "CaseLearningAsset",
    "CustomerCommunicationNotAvailableError",
    "CustomerCommunicationSimulation",
    "DataAssetSummary",
    "MetricUnit",
    "PocMetric",
    "PocSummary",
    "ReviewReport",
    "ReviewReportNotFoundError",
    "canonical_json_hash",
]
