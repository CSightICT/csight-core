"""Safe public HTTP projections for append-only analysis runs."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from app.application.analysis import AnalysisRunDetail, AnalysisRunPage
from app.platform.analysis import (
    AnalysisFailure,
    AnalysisPipeline,
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisStageRun,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    LLMExtractionResultRecord,
    LLMTextExtractionResult,
    ProviderExecutionMetadata,
)

ANALYSIS_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
)


class StartTextAnalysisRequest(BaseModel):
    """Tenant-free and idempotency-free body for starting an analysis run."""

    model_config = ANALYSIS_MODEL_CONFIG

    pipeline: AnalysisPipeline
    pipeline_version: str = Field(min_length=1, max_length=32)


class AnalysisRunListParameters(BaseModel):
    model_config = ANALYSIS_MODEL_CONFIG

    status: AnalysisRunStatus | None = None
    pipeline: AnalysisPipeline | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AnalysisFailureResponse(BaseModel):
    """Failure projection that deliberately omits internal/provider messages."""

    model_config = ANALYSIS_MODEL_CONFIG

    code: str
    retryable: bool

    @classmethod
    def from_failure(cls, failure: AnalysisFailure | None) -> Self | None:
        if failure is None:
            return None
        return cls(code=failure.code, retryable=failure.retryable)


class AnalysisRunResponse(BaseModel):
    """Run projection without idempotency, request-hash, or correlation values."""

    model_config = ANALYSIS_MODEL_CONFIG

    analysis_run_id: str
    tenant_id: str
    case_id: str
    pipeline: AnalysisPipeline
    pipeline_version: str
    trigger: AnalysisTrigger
    status: AnalysisRunStatus
    requested_by: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure: AnalysisFailureResponse | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_run(cls, run: AnalysisRun) -> Self:
        return cls(
            analysis_run_id=run.id,
            tenant_id=run.tenant_id,
            case_id=run.case_id,
            pipeline=run.pipeline,
            pipeline_version=run.pipeline_version,
            trigger=run.trigger,
            status=run.status,
            requested_by=run.requested_by,
            requested_at=run.requested_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            failure=AnalysisFailureResponse.from_failure(run.failure),
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


class ProviderExecutionResponse(BaseModel):
    """Provider metrics without the provider's internal request identifier."""

    model_config = ANALYSIS_MODEL_CONFIG

    provider_name: str
    model_name: str
    model_version: str
    model_revision: str | None
    input_token_count: int | None
    output_token_count: int | None
    latency_ms: int

    @classmethod
    def from_metadata(cls, metadata: ProviderExecutionMetadata | None) -> Self | None:
        if metadata is None:
            return None
        return cls(
            provider_name=metadata.provider_name,
            model_name=metadata.model_name,
            model_version=metadata.model_version,
            model_revision=metadata.model_revision,
            input_token_count=metadata.input_token_count,
            output_token_count=metadata.output_token_count,
            latency_ms=metadata.latency_ms,
        )


class AnalysisStageRunResponse(BaseModel):
    """Stage audit metadata without leases, claim tokens, or failure messages."""

    model_config = ANALYSIS_MODEL_CONFIG

    stage_run_id: str
    tenant_id: str
    analysis_run_id: str
    stage_type: AnalysisStageType
    status: AnalysisStageStatus
    attempt_count: int
    last_attempt_started_at: datetime | None
    last_attempt_completed_at: datetime | None
    provider_name: str
    model_name: str
    model_version: str
    model_revision: str | None
    provider_execution: ProviderExecutionResponse | None
    prompt_name: str
    prompt_version: str
    prompt_content_hash: str
    input_schema_version: str
    output_schema_version: str
    started_at: datetime | None
    completed_at: datetime | None
    failure: AnalysisFailureResponse | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_stage(cls, stage: AnalysisStageRun) -> Self:
        return cls(
            stage_run_id=stage.id,
            tenant_id=stage.tenant_id,
            analysis_run_id=stage.analysis_run_id,
            stage_type=stage.stage_type,
            status=stage.status,
            attempt_count=stage.attempt_summary.attempt_count,
            last_attempt_started_at=stage.attempt_summary.last_attempt_started_at,
            last_attempt_completed_at=stage.attempt_summary.last_attempt_completed_at,
            provider_name=stage.provider_name,
            model_name=stage.model_name,
            model_version=stage.model_version,
            model_revision=stage.model_revision,
            provider_execution=ProviderExecutionResponse.from_metadata(stage.provider_execution),
            prompt_name=stage.prompt_name,
            prompt_version=stage.prompt_version,
            prompt_content_hash=stage.prompt_content_hash,
            input_schema_version=stage.input_schema_version,
            output_schema_version=stage.output_schema_version,
            started_at=stage.started_at,
            completed_at=stage.completed_at,
            failure=AnalysisFailureResponse.from_failure(stage.failure),
            created_at=stage.created_at,
            updated_at=stage.updated_at,
        )


class LLMExtractionResultResponse(BaseModel):
    """Normalized extraction record; raw provider content is never represented."""

    model_config = ANALYSIS_MODEL_CONFIG

    extraction_result_id: str
    tenant_id: str
    analysis_run_id: str
    stage_run_id: str
    result: LLMTextExtractionResult
    created_at: datetime

    @classmethod
    def from_record(cls, record: LLMExtractionResultRecord | None) -> Self | None:
        if record is None:
            return None
        return cls(
            extraction_result_id=record.id,
            tenant_id=record.tenant_id,
            analysis_run_id=record.analysis_run_id,
            stage_run_id=record.stage_run_id,
            result=record.result,
            created_at=record.created_at,
        )


class AnalysisRunListResponse(BaseModel):
    model_config = ANALYSIS_MODEL_CONFIG

    items: tuple[AnalysisRunResponse, ...]
    page: int
    page_size: int
    total: int

    @classmethod
    def from_page(cls, page: AnalysisRunPage) -> Self:
        return cls(
            items=tuple(AnalysisRunResponse.from_run(run) for run in page.items),
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )


class AnalysisRunDetailResponse(BaseModel):
    model_config = ANALYSIS_MODEL_CONFIG

    run: AnalysisRunResponse
    stages: tuple[AnalysisStageRunResponse, ...]
    extraction_result: LLMExtractionResultResponse | None

    @classmethod
    def from_detail(cls, detail: AnalysisRunDetail) -> Self:
        return cls(
            run=AnalysisRunResponse.from_run(detail.run),
            stages=tuple(AnalysisStageRunResponse.from_stage(stage) for stage in detail.stages),
            extraction_result=LLMExtractionResultResponse.from_record(detail.extraction_result),
        )
