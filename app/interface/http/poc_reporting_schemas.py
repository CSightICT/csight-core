"""Public no-store response schemas for Review Reports and PoC metrics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.platform.case.models import JsonValue
from app.platform.poc_reporting import MetricUnit, PocMetric, PocSummary, ReviewReport


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


__all__ = ["PocMetricResponse", "PocSummaryResponse", "ReviewReportResponse"]
