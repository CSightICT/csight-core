"""Public no-store response schemas for Review Reports and PoC metrics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.platform.case.models import JsonValue
from app.platform.poc_reporting import (
    CaseLearningAsset,
    CustomerCommunicationSimulation,
    DataAssetSummary,
    MetricUnit,
    PocMetric,
    PocSummary,
    ReviewReport,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewReportResponse(_Schema):
    schema_version: str
    report_id: str
    case_id: str
    resolution_id: str
    resolution_version: int
    terminal_event_id: str
    case_snapshot: dict[str, JsonValue]
    analysis_snapshot: dict[str, JsonValue]
    policy_snapshot: dict[str, JsonValue]
    review_snapshot: dict[str, JsonValue]
    resolution_snapshot: dict[str, JsonValue]
    dry_run_snapshot: dict[str, JsonValue]
    qualification_snapshot: dict[str, JsonValue]
    data_scope: dict[str, JsonValue]
    generated_at: datetime
    content_hash: str

    @classmethod
    def from_report(cls, report: ReviewReport) -> ReviewReportResponse:
        return cls(**report.model_dump(exclude={"tenant_id"}))


class PocMetricResponse(_Schema):
    numerator: float
    denominator: int
    sample_count: int
    value: float | None
    unit: MetricUnit

    @classmethod
    def from_metric(cls, metric: PocMetric) -> PocMetricResponse:
        return cls(**metric.model_dump())


class PocSummaryResponse(_Schema):
    schema_version: str
    generated_at: datetime
    eligible_source_scope: str
    eligible_case_count: int
    excluded_case_count: int
    review_time: PocMetricResponse
    recommendation_difference_rate: PocMetricResponse
    additional_evidence_request_rate: PocMetricResponse
    action_input_missing_rate: PocMetricResponse
    dry_run_success_rate: PocMetricResponse
    analysis_failure_rate: PocMetricResponse
    analysis_partial_success_rate: PocMetricResponse

    @classmethod
    def from_summary(cls, summary: PocSummary) -> PocSummaryResponse:
        return cls(
            schema_version=summary.schema_version,
            generated_at=summary.generated_at,
            eligible_source_scope=summary.eligible_source_scope,
            eligible_case_count=summary.eligible_case_count,
            excluded_case_count=summary.excluded_case_count,
            review_time=PocMetricResponse.from_metric(summary.review_time),
            recommendation_difference_rate=PocMetricResponse.from_metric(
                summary.recommendation_difference_rate
            ),
            additional_evidence_request_rate=PocMetricResponse.from_metric(
                summary.additional_evidence_request_rate
            ),
            action_input_missing_rate=PocMetricResponse.from_metric(
                summary.action_input_missing_rate
            ),
            dry_run_success_rate=PocMetricResponse.from_metric(summary.dry_run_success_rate),
            analysis_failure_rate=PocMetricResponse.from_metric(summary.analysis_failure_rate),
            analysis_partial_success_rate=PocMetricResponse.from_metric(
                summary.analysis_partial_success_rate
            ),
        )


class CustomerCommunicationResponse(_Schema):
    schema_version: str
    communication_id: str
    case_id: str
    review_report_id: str
    channel: str
    template_name: str
    template_version: str
    recipient_label: str
    subject: str
    body: str
    delivery_status: str
    side_effects_performed: bool
    created_at: datetime
    content_hash: str

    @classmethod
    def from_simulation(
        cls, simulation: CustomerCommunicationSimulation
    ) -> CustomerCommunicationResponse:
        return cls(**simulation.model_dump(exclude={"tenant_id", "created_by"}))


class CaseLearningAssetResponse(_Schema):
    schema_version: str
    asset_id: str
    case_id: str
    review_report_id: str
    feature_snapshot: dict[str, JsonValue]
    label_snapshot: dict[str, JsonValue]
    version_snapshot: dict[str, JsonValue]
    privacy_scope: dict[str, JsonValue]
    created_at: datetime
    content_hash: str

    @classmethod
    def from_asset(cls, asset: CaseLearningAsset) -> CaseLearningAssetResponse:
        return cls(**asset.model_dump(exclude={"tenant_id", "subject_pseudonym"}))


class DataAssetSummaryResponse(_Schema):
    schema_version: str
    generated_at: datetime
    total_records: int
    eligible_records: int
    excluded_records: int
    eligible_source_scope: str
    source_scope_distribution: dict[str, int]
    baseline_minimum: int
    drift_review_minimum: int
    readiness_status: str
    drift_evaluation_available: bool
    decision_distribution: dict[str, int]
    resolution_distribution: dict[str, int]
    product_distribution: dict[str, int]
    model_version_distribution: dict[str, int]
    policy_version_distribution: dict[str, int]
    recent_records: list[CaseLearningAssetResponse]

    @classmethod
    def from_summary(cls, summary: DataAssetSummary) -> DataAssetSummaryResponse:
        return cls(
            **summary.model_dump(exclude={"recent_records"}),
            recent_records=[
                CaseLearningAssetResponse.from_asset(item) for item in summary.recent_records
            ],
        )


__all__ = [
    "CaseLearningAssetResponse",
    "CustomerCommunicationResponse",
    "DataAssetSummaryResponse",
    "PocMetricResponse",
    "PocSummaryResponse",
    "ReviewReportResponse",
]
