"""Application services for append-only text-analysis runs."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.analysis import (
    TEXT_EXTRACTION_PIPELINE_VERSION,
    AnalysisAttemptStatus,
    AnalysisAttemptSummary,
    AnalysisFailure,
    AnalysisMaxRetriesExceededError,
    AnalysisPipeline,
    AnalysisPipelineNotSupportedError,
    AnalysisProviderError,
    AnalysisRequestedEvent,
    AnalysisRequestIdempotencyRecord,
    AnalysisRun,
    AnalysisRunNotFoundError,
    AnalysisRunStatus,
    AnalysisStageAttempt,
    AnalysisStageRun,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    CustomerRequest,
    LLMExtractionResultRecord,
    LLMProviderRequestRejectedError,
    LLMTextExtractionRequest,
    OutboxEvent,
    OutboxStatus,
    PromptManifest,
)
from app.platform.errors import (
    CaseNotFoundError,
    IdempotencyKeyReusedError,
    InconsistentPersistenceStateError,
)
from app.platform.tenant import Permission, Principal
from app.ports.analysis_repository import (
    AnalysisRunListCriteria,
    AnalysisUnitOfWork,
    AnalysisUnitOfWorkFactory,
)
from app.ports.llm import LLMProvider
from app.ports.runtime import Clock, IdGenerator

CREATE_ANALYSIS_OPERATION = "analysis.create.v1"
ANALYSIS_REQUESTED_EVENT_TYPE = "analysis.requested.v1"
ANALYSIS_REQUESTED_EVENT_VERSION = "1.0"
ANALYSIS_IDEMPOTENCY_RETENTION = timedelta(hours=24)
DEFAULT_CLAIM_TTL = timedelta(minutes=5)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE = timedelta(seconds=5)
DEFAULT_RETRY_MAX = timedelta(minutes=5)
DEFAULT_RETRY_JITTER_RATIO = 0.2


class _ApplicationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StartTextAnalysisCommand(_ApplicationDTO):
    pipeline: AnalysisPipeline
    pipeline_version: str = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    correlation_id: str = Field(min_length=1, max_length=128)


class StartTextAnalysisResult(_ApplicationDTO):
    run: AnalysisRun
    replayed: bool = False


class ListAnalysisRunsQuery(_ApplicationDTO):
    status: AnalysisRunStatus | None = None
    pipeline: AnalysisPipeline | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    def criteria(self) -> AnalysisRunListCriteria:
        return AnalysisRunListCriteria(**self.model_dump())


class AnalysisRunPage(_ApplicationDTO):
    items: tuple[AnalysisRun, ...]
    page: int
    page_size: int
    total: int


class AnalysisRunDetail(_ApplicationDTO):
    run: AnalysisRun
    stages: tuple[AnalysisStageRun, ...]
    extraction_result: LLMExtractionResultRecord | None


class ExecuteTextExtractionCommand(_ApplicationDTO):
    """The complete and only payload accepted by the worker use case."""

    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=128)


class ExecutionDisposition(StrEnum):
    NOOP = "NOOP"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAITING = "RETRY_WAITING"
    FAILED = "FAILED"


class ExecuteTextExtractionResult(_ApplicationDTO):
    disposition: ExecutionDisposition
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    status: AnalysisStageStatus | None
    retry_at: datetime | None = None

    @field_validator("retry_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retry_at must be timezone-aware")
        return value.astimezone(UTC)


def canonical_analysis_request_hash(
    *,
    case_id: str,
    command: StartTextAnalysisCommand,
) -> str:
    """Hash only behavior-bearing request fields, excluding retry metadata."""

    payload = {
        "case_id": case_id,
        "pipeline": command.pipeline.value,
        "pipeline_version": command.pipeline_version,
        "trigger": AnalysisTrigger.USER_REQUEST.value,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deterministic_retry_delay(
    *,
    attempt_number: int,
    seed: str,
    base: timedelta,
    maximum: timedelta,
    jitter_ratio: float,
) -> timedelta:
    """Return bounded exponential backoff with stable, centered jitter."""

    if attempt_number < 1:
        raise ValueError("attempt_number must be positive")
    if base.total_seconds() <= 0 or maximum.total_seconds() <= 0:
        raise ValueError("retry durations must be positive")
    if base > maximum:
        raise ValueError("retry base must not exceed retry maximum")
    if not 0 <= jitter_ratio <= 1:
        raise ValueError("jitter_ratio must be between zero and one")

    unjittered = min(
        maximum.total_seconds(),
        base.total_seconds() * (2 ** (attempt_number - 1)),
    )
    digest = hashlib.sha256(f"{seed}:{attempt_number}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    centered = (unit * 2) - 1
    seconds = unjittered * (1 + (centered * jitter_ratio))
    seconds = min(maximum.total_seconds(), max(0.001, seconds))
    return timedelta(seconds=seconds)


class StartTextAnalysis:
    def __init__(
        self,
        *,
        uow_factory: AnalysisUnitOfWorkFactory,
        provider: LLMProvider,
        prompt: PromptManifest,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider
        self._prompt = prompt
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartTextAnalysisCommand,
    ) -> StartTextAnalysisResult:
        if (
            command.pipeline is not AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION
            or command.pipeline_version != TEXT_EXTRACTION_PIPELINE_VERSION
        ):
            raise AnalysisPipelineNotSupportedError()
        now = self._clock.now().astimezone(UTC)
        request_hash = canonical_analysis_request_hash(case_id=case_id, command=command)
        run_id = self._id_generator.new_id()
        stage_run_id = self._id_generator.new_id()
        event_id = self._id_generator.new_id()
        provider = self._provider.provider_metadata

        run = AnalysisRun(
            id=run_id,
            tenant_id=principal.tenant_id,
            case_id=case_id,
            pipeline=command.pipeline,
            pipeline_version=command.pipeline_version,
            trigger=AnalysisTrigger.USER_REQUEST,
            status=AnalysisRunStatus.QUEUED,
            requested_by=principal.user_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        stage = AnalysisStageRun(
            id=stage_run_id,
            tenant_id=principal.tenant_id,
            analysis_run_id=run_id,
            stage_type=AnalysisStageType.TEXT_EXTRACTION,
            status=AnalysisStageStatus.QUEUED,
            attempt_summary=AnalysisAttemptSummary(),
            provider_name=provider.provider,
            model_name=provider.name,
            model_version=provider.version,
            model_revision=provider.revision,
            prompt_name=self._prompt.name,
            prompt_version=self._prompt.version,
            prompt_content_hash=self._prompt.content_hash,
            input_schema_version=self._prompt.input_schema_version,
            output_schema_version=self._prompt.output_schema_version,
            created_at=now,
            updated_at=now,
        )
        requested_event = AnalysisRequestedEvent(
            event_id=event_id,
            tenant_id=principal.tenant_id,
            case_id=case_id,
            analysis_run_id=run_id,
            stage_run_id=stage_run_id,
            correlation_id=command.correlation_id,
            occurred_at=now,
        )
        outbox_event = _pending_outbox_event(event=requested_event, now=now)
        idempotency_record = AnalysisRequestIdempotencyRecord(
            id=self._id_generator.new_id(),
            tenant_id=principal.tenant_id,
            case_id=case_id,
            operation=CREATE_ANALYSIS_OPERATION,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            analysis_run_id=run_id,
            response_status=202,
            created_at=now,
            expires_at=now + ANALYSIS_IDEMPOTENCY_RETENTION,
        )

        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
            if case is None:
                raise CaseNotFoundError()
            principal.require(Permission.ANALYSIS_CREATE)

            claim = uow.request_idempotency.claim(
                tenant_id=principal.tenant_id,
                record=idempotency_record,
            )
            if not claim.claimed:
                if claim.record.request_hash != request_hash:
                    raise IdempotencyKeyReusedError()
                existing = uow.analysis_runs.get(
                    tenant_id=principal.tenant_id,
                    case_id=claim.record.case_id,
                    analysis_run_id=claim.record.analysis_run_id,
                )
                if existing is None:
                    raise InconsistentPersistenceStateError()
                return StartTextAnalysisResult(run=existing, replayed=True)

            uow.analysis_runs.add(tenant_id=principal.tenant_id, run=run)
            uow.stage_runs.add(tenant_id=principal.tenant_id, stage_run=stage)
            uow.outbox.add(tenant_id=principal.tenant_id, event=outbox_event)
            uow.flush()
            uow.commit()
        return StartTextAnalysisResult(run=run)


class ListAnalysisRuns:
    def __init__(self, *, uow_factory: AnalysisUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        query: ListAnalysisRunsQuery,
    ) -> AnalysisRunPage:
        criteria = query.criteria()
        with self._uow_factory() as uow:
            _require_case_then_permission(
                uow=uow,
                principal=principal,
                case_id=case_id,
                permission=Permission.ANALYSIS_READ,
            )
            items = uow.analysis_runs.list(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                criteria=criteria,
            )
            total = uow.analysis_runs.count(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                criteria=criteria,
            )
        return AnalysisRunPage(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total=total,
        )


class GetAnalysisRun:
    def __init__(self, *, uow_factory: AnalysisUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRunDetail:
        with self._uow_factory() as uow:
            _require_case_then_permission(
                uow=uow,
                principal=principal,
                case_id=case_id,
                permission=Permission.ANALYSIS_READ,
            )
            run = uow.analysis_runs.get(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                analysis_run_id=analysis_run_id,
            )
            if run is None:
                raise AnalysisRunNotFoundError()
            return _detail(uow=uow, tenant_id=principal.tenant_id, run=run)


class GetLatestAnalysisRun:
    def __init__(self, *, uow_factory: AnalysisUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, principal: Principal, case_id: str) -> AnalysisRun | None:
        with self._uow_factory() as uow:
            _require_case_then_permission(
                uow=uow,
                principal=principal,
                case_id=case_id,
                permission=Permission.ANALYSIS_READ,
            )
            run = uow.analysis_runs.latest(tenant_id=principal.tenant_id, case_id=case_id)
            return run


class ExecuteTextExtraction:
    def __init__(
        self,
        *,
        uow_factory: AnalysisUnitOfWorkFactory,
        provider: LLMProvider,
        prompt: PromptManifest,
        clock: Clock,
        id_generator: IdGenerator,
        claim_ttl: timedelta = DEFAULT_CLAIM_TTL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_base: timedelta = DEFAULT_RETRY_BASE,
        retry_max: timedelta = DEFAULT_RETRY_MAX,
        retry_jitter_ratio: float = DEFAULT_RETRY_JITTER_RATIO,
    ) -> None:
        if claim_ttl.total_seconds() <= 0:
            raise ValueError("claim_ttl must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        deterministic_retry_delay(
            attempt_number=1,
            seed="configuration",
            base=retry_base,
            maximum=retry_max,
            jitter_ratio=retry_jitter_ratio,
        )
        self._uow_factory = uow_factory
        self._provider = provider
        self._prompt = prompt
        self._clock = clock
        self._id_generator = id_generator
        self._claim_ttl = claim_ttl
        self._max_attempts = max_attempts
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._retry_jitter_ratio = retry_jitter_ratio

    def execute(
        self,
        *,
        command: ExecuteTextExtractionCommand,
    ) -> ExecuteTextExtractionResult:
        claim_token = self._id_generator.new_id()
        now = self._clock.now().astimezone(UTC)

        with self._uow_factory() as uow:
            run = uow.analysis_runs.get(
                tenant_id=command.tenant_id,
                case_id=command.case_id,
                analysis_run_id=command.analysis_run_id,
            )
            stage = uow.stage_runs.get(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
            )
            if run is None or stage is None:
                return _execution_result(command=command, status=None)
            if run.status.is_terminal or stage.status.is_terminal:
                return _execution_result(command=command, status=stage.status)
            if stage.stage_type is not AnalysisStageType.TEXT_EXTRACTION:
                return _execution_result(command=command, status=stage.status)

            existing_result = uow.extraction_results.get_by_run(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
            )
            if existing_result is not None:
                return _execution_result(command=command, status=stage.status)

            if (
                stage.status is AnalysisStageStatus.RUNNING
                and stage.claim_token is not None
                and stage.claim_expires_at is not None
                and stage.claim_expires_at <= now
                and stage.attempt_summary.attempt_count >= self._max_attempts
            ):
                return self._fail_expired_attempt_limit(
                    uow=uow,
                    command=command,
                    run=run,
                    stage=stage,
                    now=now,
                )

            case = uow.cases.get(tenant_id=command.tenant_id, case_id=command.case_id)
            if case is None:
                raise InconsistentPersistenceStateError()
            claimed_stage = uow.stage_runs.claim_for_execution(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
                claim_token=claim_token,
                now=now,
                claim_expires_at=now + self._claim_ttl,
            )
            if claimed_stage is None:
                if (
                    stage.status is AnalysisStageStatus.RUNNING
                    and stage.claim_expires_at is not None
                    and stage.claim_expires_at > now
                ):
                    # A worker-lost redelivery can arrive before the previous
                    # execution lease expires.  Persist one future, reference-only
                    # wake-up so acknowledging this duplicate cannot strand the
                    # stage in RUNNING forever.  A healthy original worker makes
                    # that later delivery a harmless terminal no-op.
                    recovery_event = AnalysisRequestedEvent(
                        event_id=self._id_generator.new_id(),
                        tenant_id=command.tenant_id,
                        case_id=command.case_id,
                        analysis_run_id=command.analysis_run_id,
                        stage_run_id=command.stage_run_id,
                        correlation_id=command.correlation_id,
                        occurred_at=now,
                    )
                    uow.outbox.add(
                        tenant_id=command.tenant_id,
                        event=_pending_outbox_event(
                            event=recovery_event,
                            now=now,
                            available_at=stage.claim_expires_at,
                        ),
                    )
                    uow.flush()
                    uow.commit()
                return _execution_result(command=command, status=stage.status)

            stale_failure = AnalysisFailure(
                code="ANALYSIS_ATTEMPT_LEASE_EXPIRED",
                message="The previous text-extraction attempt lease expired.",
                retryable=True,
            )
            uow.stage_attempts.abandon_stale(
                tenant_id=command.tenant_id,
                stage_run_id=command.stage_run_id,
                stale_before=now,
                abandoned_at=now,
                failure=stale_failure,
            )
            if run.status in {AnalysisRunStatus.QUEUED, AnalysisRunStatus.RETRY_WAITING}:
                transitioned_run = uow.analysis_runs.transition(
                    tenant_id=command.tenant_id,
                    analysis_run_id=command.analysis_run_id,
                    expected_status=run.status,
                    target_status=AnalysisRunStatus.RUNNING,
                    now=now,
                )
                if transitioned_run is None:
                    uow.rollback()
                    return _execution_result(command=command, status=stage.status)
            elif run.status is not AnalysisRunStatus.RUNNING:
                uow.rollback()
                return _execution_result(command=command, status=stage.status)

            attempt_number = claimed_stage.attempt_summary.attempt_count
            attempt = _new_attempt(
                stage=claimed_stage,
                attempt_id=self._id_generator.new_id(),
                claim_token=claim_token,
                attempt_number=attempt_number,
                now=now,
            )
            uow.stage_attempts.add(tenant_id=command.tenant_id, attempt=attempt)
            uow.flush()
            uow.commit()

        request = LLMTextExtractionRequest(
            customer_message=case.customer_message,
            order_ref=case.order_ref,
            product_ref=case.product_ref,
            requested_action=CustomerRequest(case.requested_action.value),
        )
        try:
            self._require_execution_snapshot(stage=claimed_stage)
            response = self._provider.extract_text(request, self._prompt)
            self._require_response_snapshot(stage=claimed_stage, response=response.metadata)
            response.result.require_exact_source_quotes(
                customer_message=request.customer_message,
                provider=claimed_stage.provider_name,
            )
        except AnalysisProviderError as error:
            return self._persist_provider_failure(
                command=command,
                claim_token=claim_token,
                attempt_number=attempt_number,
                error=error,
            )

        completed_at = self._clock.now().astimezone(UTC)
        result_record = LLMExtractionResultRecord(
            id=self._id_generator.new_id(),
            tenant_id=command.tenant_id,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            result=response.result,
            created_at=completed_at,
        )
        with self._uow_factory() as uow:
            existing_result = uow.extraction_results.get_by_run(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
            )
            if existing_result is not None:
                return _execution_result(command=command, status=AnalysisStageStatus.SUCCEEDED)
            current_run = uow.analysis_runs.get(
                tenant_id=command.tenant_id,
                case_id=command.case_id,
                analysis_run_id=command.analysis_run_id,
            )
            current_stage = uow.stage_runs.get(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
            )
            if current_run is None or current_stage is None:
                return _execution_result(command=command, status=None)
            transitioned_stage = uow.stage_runs.transition_if_claimed(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
                claim_token=claim_token,
                target_status=AnalysisStageStatus.SUCCEEDED,
                now=completed_at,
                provider_execution=response.metadata,
            )
            if transitioned_stage is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)
            finalized_attempt = uow.stage_attempts.finalize_if_claimed(
                tenant_id=command.tenant_id,
                stage_run_id=command.stage_run_id,
                attempt_number=attempt_number,
                claim_token=claim_token,
                target_status=AnalysisAttemptStatus.SUCCEEDED,
                completed_at=completed_at,
                provider_execution=response.metadata,
            )
            if finalized_attempt is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)
            transitioned_run = uow.analysis_runs.transition(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                expected_status=AnalysisRunStatus.RUNNING,
                target_status=AnalysisRunStatus.SUCCEEDED,
                now=completed_at,
            )
            if transitioned_run is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)
            uow.extraction_results.add(tenant_id=command.tenant_id, result=result_record)
            uow.flush()
            uow.commit()
        return ExecuteTextExtractionResult(
            disposition=ExecutionDisposition.SUCCEEDED,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            status=AnalysisStageStatus.SUCCEEDED,
        )

    def _fail_expired_attempt_limit(
        self,
        *,
        uow: AnalysisUnitOfWork,
        command: ExecuteTextExtractionCommand,
        run: AnalysisRun,
        stage: AnalysisStageRun,
        now: datetime,
    ) -> ExecuteTextExtractionResult:
        """Finish an expired final lease without starting an unbounded attempt."""

        claim_token = stage.claim_token
        if claim_token is None:
            raise InconsistentPersistenceStateError()
        failure = AnalysisFailure(
            code=AnalysisMaxRetriesExceededError.code,
            message="The text-extraction attempt limit was reached after a worker lease expired.",
            retryable=False,
        )
        transitioned_stage = uow.stage_runs.transition_if_claimed(
            tenant_id=command.tenant_id,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            claim_token=claim_token,
            target_status=AnalysisStageStatus.FAILED,
            now=now,
            failure=failure,
        )
        finalized_attempt = uow.stage_attempts.finalize_if_claimed(
            tenant_id=command.tenant_id,
            stage_run_id=command.stage_run_id,
            attempt_number=stage.attempt_summary.attempt_count,
            claim_token=claim_token,
            target_status=AnalysisAttemptStatus.ABANDONED,
            completed_at=now,
            failure=failure,
        )
        transitioned_run = uow.analysis_runs.transition(
            tenant_id=command.tenant_id,
            analysis_run_id=command.analysis_run_id,
            expected_status=run.status,
            target_status=AnalysisRunStatus.FAILED,
            now=now,
            failure=failure,
        )
        if finalized_attempt is None or transitioned_stage is None or transitioned_run is None:
            uow.rollback()
            return _execution_result(command=command, status=stage.status)
        uow.flush()
        uow.commit()
        return ExecuteTextExtractionResult(
            disposition=ExecutionDisposition.FAILED,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            status=AnalysisStageStatus.FAILED,
        )

    def _require_execution_snapshot(self, *, stage: AnalysisStageRun) -> None:
        provider = self._provider.provider_metadata
        provider_snapshot = (
            provider.provider,
            provider.name,
            provider.version,
            provider.revision,
        )
        stage_provider_snapshot = (
            stage.provider_name,
            stage.model_name,
            stage.model_version,
            stage.model_revision,
        )
        prompt_snapshot = (
            self._prompt.name,
            self._prompt.version,
            self._prompt.content_hash,
            self._prompt.input_schema_version,
            self._prompt.output_schema_version,
        )
        stage_prompt_snapshot = (
            stage.prompt_name,
            stage.prompt_version,
            stage.prompt_content_hash,
            stage.input_schema_version,
            stage.output_schema_version,
        )
        if provider_snapshot != stage_provider_snapshot or prompt_snapshot != stage_prompt_snapshot:
            raise LLMProviderRequestRejectedError(
                provider=provider.provider,
                message="the configured execution snapshot does not match the registered stage",
            )

    def _require_response_snapshot(self, *, stage: AnalysisStageRun, response: object) -> None:
        from app.platform.analysis import ProviderExecutionMetadata

        if not isinstance(response, ProviderExecutionMetadata):
            raise LLMProviderRequestRejectedError(
                provider=stage.provider_name,
                message="the provider returned invalid execution metadata",
            )
        response_snapshot = (
            response.provider_name,
            response.model_name,
            response.model_version,
            response.model_revision,
        )
        stage_snapshot = (
            stage.provider_name,
            stage.model_name,
            stage.model_version,
            stage.model_revision,
        )
        if response_snapshot != stage_snapshot:
            raise LLMProviderRequestRejectedError(
                provider=stage.provider_name,
                message="the provider response does not match the registered model snapshot",
            )

    def _persist_provider_failure(
        self,
        *,
        command: ExecuteTextExtractionCommand,
        claim_token: str,
        attempt_number: int,
        error: AnalysisProviderError,
    ) -> ExecuteTextExtractionResult:
        now = self._clock.now().astimezone(UTC)
        retryable = error.retryable and attempt_number < self._max_attempts
        if error.retryable and not retryable:
            code = AnalysisMaxRetriesExceededError.code
            message = "The text-extraction attempt limit was reached."
        else:
            code = error.code
            message = "The text-extraction provider could not complete the attempt."
        failure = AnalysisFailure(code=code, message=message, retryable=retryable)
        retry_at = None
        if retryable:
            retry_at = now + deterministic_retry_delay(
                attempt_number=attempt_number,
                seed=command.stage_run_id,
                base=self._retry_base,
                maximum=self._retry_max,
                jitter_ratio=self._retry_jitter_ratio,
            )
        target_stage = (
            AnalysisStageStatus.RETRY_WAITING if retryable else AnalysisStageStatus.FAILED
        )
        target_run = AnalysisRunStatus.RETRY_WAITING if retryable else AnalysisRunStatus.FAILED
        target_attempt = (
            AnalysisAttemptStatus.RETRY_WAITING if retryable else AnalysisAttemptStatus.FAILED
        )

        with self._uow_factory() as uow:
            current_run = uow.analysis_runs.get(
                tenant_id=command.tenant_id,
                case_id=command.case_id,
                analysis_run_id=command.analysis_run_id,
            )
            current_stage = uow.stage_runs.get(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
            )
            if current_run is None or current_stage is None:
                return _execution_result(command=command, status=None)
            transitioned_stage = uow.stage_runs.transition_if_claimed(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                stage_run_id=command.stage_run_id,
                claim_token=claim_token,
                target_status=target_stage,
                now=now,
                next_attempt_at=retry_at,
                failure=failure,
            )
            if transitioned_stage is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)
            finalized_attempt = uow.stage_attempts.finalize_if_claimed(
                tenant_id=command.tenant_id,
                stage_run_id=command.stage_run_id,
                attempt_number=attempt_number,
                claim_token=claim_token,
                target_status=target_attempt,
                completed_at=now,
                failure=failure,
            )
            if finalized_attempt is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)
            transitioned_run = uow.analysis_runs.transition(
                tenant_id=command.tenant_id,
                analysis_run_id=command.analysis_run_id,
                expected_status=AnalysisRunStatus.RUNNING,
                target_status=target_run,
                now=now,
                failure=failure,
            )
            if transitioned_run is None:
                uow.rollback()
                return _execution_result(command=command, status=current_stage.status)

            if retry_at is not None:
                retry_event = AnalysisRequestedEvent(
                    event_id=self._id_generator.new_id(),
                    tenant_id=command.tenant_id,
                    case_id=command.case_id,
                    analysis_run_id=command.analysis_run_id,
                    stage_run_id=command.stage_run_id,
                    correlation_id=command.correlation_id,
                    occurred_at=now,
                )
                uow.outbox.add(
                    tenant_id=command.tenant_id,
                    event=_pending_outbox_event(
                        event=retry_event,
                        now=now,
                        available_at=retry_at,
                    ),
                )
            uow.flush()
            uow.commit()
        disposition = (
            ExecutionDisposition.RETRY_WAITING if retryable else ExecutionDisposition.FAILED
        )
        return ExecuteTextExtractionResult(
            disposition=disposition,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            status=target_stage,
            retry_at=retry_at,
        )


def _require_case_then_permission(
    *,
    uow: AnalysisUnitOfWork,
    principal: Principal,
    case_id: str,
    permission: Permission,
) -> None:
    case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
    if case is None:
        raise CaseNotFoundError()
    principal.require(permission)


def _detail(
    *,
    uow: AnalysisUnitOfWork,
    tenant_id: str,
    run: AnalysisRun,
) -> AnalysisRunDetail:
    return AnalysisRunDetail(
        run=run,
        stages=uow.stage_runs.list(tenant_id=tenant_id, analysis_run_id=run.id),
        extraction_result=uow.extraction_results.get_by_run(
            tenant_id=tenant_id,
            analysis_run_id=run.id,
        ),
    )


def _new_attempt(
    *,
    stage: AnalysisStageRun,
    attempt_id: str,
    claim_token: str,
    attempt_number: int,
    now: datetime,
) -> AnalysisStageAttempt:
    return AnalysisStageAttempt(
        id=attempt_id,
        tenant_id=stage.tenant_id,
        analysis_run_id=stage.analysis_run_id,
        stage_run_id=stage.id,
        attempt_number=attempt_number,
        status=AnalysisAttemptStatus.RUNNING,
        claim_token=claim_token,
        provider_name=stage.provider_name,
        model_name=stage.model_name,
        model_version=stage.model_version,
        model_revision=stage.model_revision,
        prompt_name=stage.prompt_name,
        prompt_version=stage.prompt_version,
        prompt_content_hash=stage.prompt_content_hash,
        input_schema_version=stage.input_schema_version,
        output_schema_version=stage.output_schema_version,
        started_at=now,
        created_at=now,
    )


def _pending_outbox_event(
    *,
    event: AnalysisRequestedEvent,
    now: datetime,
    available_at: datetime | None = None,
) -> OutboxEvent:
    return OutboxEvent(
        id=event.event_id,
        tenant_id=event.tenant_id,
        aggregate_type="analysis_run",
        aggregate_id=event.analysis_run_id,
        event_type=ANALYSIS_REQUESTED_EVENT_TYPE,
        event_version=ANALYSIS_REQUESTED_EVENT_VERSION,
        payload=event.model_dump(mode="json"),
        status=OutboxStatus.PENDING,
        available_at=available_at or now,
        created_at=now,
        updated_at=now,
    )


def _execution_result(
    *,
    command: ExecuteTextExtractionCommand,
    status: AnalysisStageStatus | None,
) -> ExecuteTextExtractionResult:
    return ExecuteTextExtractionResult(
        disposition=ExecutionDisposition.NOOP,
        analysis_run_id=command.analysis_run_id,
        stage_run_id=command.stage_run_id,
        status=status,
    )


__all__ = [
    "ANALYSIS_REQUESTED_EVENT_TYPE",
    "AnalysisRunDetail",
    "AnalysisRunPage",
    "ExecuteTextExtraction",
    "ExecuteTextExtractionCommand",
    "ExecuteTextExtractionResult",
    "ExecutionDisposition",
    "GetAnalysisRun",
    "GetLatestAnalysisRun",
    "ListAnalysisRuns",
    "ListAnalysisRunsQuery",
    "StartTextAnalysis",
    "StartTextAnalysisCommand",
    "StartTextAnalysisResult",
    "canonical_analysis_request_hash",
    "deterministic_retry_delay",
]
