"""SQLAlchemy adapter for immutable citation packs and grounded explanations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    GroundedExplanationOutboxEventModel,
    GroundedExplanationResultModel,
    GroundedExplanationRunModel,
    GroundingProfileModel,
    LLMExtractionResultV2Model,
    PolicyCitationPackItemModel,
    PolicyCitationPackModel,
    PolicyClauseModel,
    PolicyRetrievalRunHitModel,
    PolicyRetrievalRunModel,
)
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.errors import CaseNotFoundError, IdempotencyKeyReusedError, ValidationError
from app.platform.grounding import (
    CitationPack,
    CitationSnapshot,
    GroundedExplanationRun,
    GroundedExplanationRunStatus,
    GroundedPolicyExplanation,
    GroundingValidationMetrics,
)
from app.platform.policy_reference import ClauseType
from app.platform.policy_retrieval import stable_json_hash
from app.platform.query_builder import QueryStrategy
from app.ports.grounding import GroundedExplanationExecutionSource, GroundedExplanationRunDetail

_NAMESPACE = UUID("f2315a75-a952-4f0f-8705-5db3fd68fa7c")


class SQLAlchemyGroundedExplanationRunRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        retrieval_run_id: str,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        provider: ProviderExecutionMetadata,
        prompt_name: str,
        prompt_version: str,
        prompt_hash: str,
    ) -> tuple[GroundedExplanationRun, bool]:
        tenant_uuid, case_uuid, retrieval_uuid = map(UUID, (tenant_id, case_id, retrieval_run_id))
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            existing = session.scalar(
                select(GroundedExplanationRunModel).where(
                    GroundedExplanationRunModel.tenant_id == tenant_uuid,
                    GroundedExplanationRunModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyKeyReusedError()
                return _to_run(existing), True
            retrieval = session.scalar(
                select(PolicyRetrievalRunModel).where(
                    PolicyRetrievalRunModel.tenant_id == tenant_uuid,
                    PolicyRetrievalRunModel.case_id == case_uuid,
                    PolicyRetrievalRunModel.id == retrieval_uuid,
                    PolicyRetrievalRunModel.status == "SUCCEEDED",
                )
            )
            if retrieval is None:
                raise CaseNotFoundError("A successful policy retrieval run was not found.")
            pack = _get_or_create_pack(session, retrieval, now)
            profile = _ensure_profile(
                session,
                provider=provider,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
            )
            run_row = GroundedExplanationRunModel(
                id=uuid4(),
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                retrieval_run_id=retrieval_uuid,
                citation_pack_id=UUID(pack.id),
                grounding_profile_id=profile.id,
                status="QUEUED",
                requested_by=UUID(requested_by),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                started_at=None,
                completed_at=None,
                failure_code=None,
                failure_message=None,
                created_at=now,
            )
            session.add(run_row)
            session.flush()
            session.add(
                GroundedExplanationOutboxEventModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    grounded_explanation_run_id=run_row.id,
                    correlation_id=correlation_id,
                    status="PENDING",
                    attempt_count=0,
                    available_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return _to_run(run_row), False

    def list(self, *, tenant_id: str, case_id: str) -> tuple[GroundedExplanationRun, ...]:
        with self._factory() as session:
            rows = session.scalars(
                select(GroundedExplanationRunModel)
                .where(
                    GroundedExplanationRunModel.tenant_id == UUID(tenant_id),
                    GroundedExplanationRunModel.case_id == UUID(case_id),
                )
                .order_by(
                    GroundedExplanationRunModel.created_at.desc(),
                    GroundedExplanationRunModel.id,
                )
            ).all()
            return tuple(_to_run(row) for row in rows)

    def get(
        self, *, tenant_id: str, case_id: str, run_id: str
    ) -> GroundedExplanationRunDetail | None:
        with self._factory() as session:
            row = session.scalar(
                select(GroundedExplanationRunModel).where(
                    GroundedExplanationRunModel.tenant_id == UUID(tenant_id),
                    GroundedExplanationRunModel.case_id == UUID(case_id),
                    GroundedExplanationRunModel.id == UUID(run_id),
                )
            )
            if row is None:
                return None
            pack = _load_pack(session, row.tenant_id, row.citation_pack_id)
            result = session.scalar(
                select(GroundedExplanationResultModel).where(
                    GroundedExplanationResultModel.tenant_id == row.tenant_id,
                    GroundedExplanationResultModel.grounded_explanation_run_id == row.id,
                )
            )
            return GroundedExplanationRunDetail(
                run=_to_run(row),
                citation_pack=pack,
                explanation=(
                    GroundedPolicyExplanation.model_validate(
                        {
                            "schema_version": result.schema_version,
                            "summary": result.summary,
                            "policy_statements": result.policy_statements,
                            "unresolved_conditions": result.unresolved_conditions,
                        }
                    )
                    if result is not None
                    else None
                ),
                validation_metrics=(
                    GroundingValidationMetrics.model_validate(result.validation_metrics)
                    if result is not None
                    else None
                ),
            )

    def claim(self, *, tenant_id: str, run_id: str) -> GroundedExplanationExecutionSource | None:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        with self._factory.begin() as session:
            claimed = session.execute(
                update(GroundedExplanationRunModel)
                .where(
                    GroundedExplanationRunModel.tenant_id == tenant_uuid,
                    GroundedExplanationRunModel.id == run_uuid,
                    GroundedExplanationRunModel.status == "QUEUED",
                )
                .values(status="RUNNING", started_at=datetime.now(UTC))
                .returning(GroundedExplanationRunModel.id)
            ).scalar_one_or_none()
            if claimed is None:
                return None
            row = session.get(GroundedExplanationRunModel, run_uuid)
            assert row is not None
            retrieval = session.get(PolicyRetrievalRunModel, row.retrieval_run_id)
            assert retrieval is not None
            extraction = session.get(LLMExtractionResultV2Model, retrieval.text_result_id)
            assert extraction is not None
            return GroundedExplanationExecutionSource(
                run=_to_run(row),
                case_summary=extraction.summary,
                citation_pack=_load_pack(session, tenant_uuid, row.citation_pack_id),
            )

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        explanation: GroundedPolicyExplanation,
        metrics: GroundingValidationMetrics,
        provider: ProviderExecutionMetadata,
        prompt_name: str,
        prompt_version: str,
        prompt_hash: str,
    ) -> None:
        tenant_uuid, run_uuid = UUID(tenant_id), UUID(run_id)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            run = session.scalar(
                select(GroundedExplanationRunModel).where(
                    GroundedExplanationRunModel.tenant_id == tenant_uuid,
                    GroundedExplanationRunModel.id == run_uuid,
                    GroundedExplanationRunModel.status == "RUNNING",
                )
            )
            if run is None:
                return
            session.add(
                GroundedExplanationResultModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    grounded_explanation_run_id=run_uuid,
                    schema_version=explanation.schema_version,
                    summary=explanation.summary,
                    policy_statements=[
                        value.model_dump(mode="json") for value in explanation.policy_statements
                    ],
                    unresolved_conditions=[
                        value.model_dump(mode="json") for value in explanation.unresolved_conditions
                    ],
                    validation_metrics=metrics.model_dump(mode="json"),
                    provider_name=provider.provider_name,
                    model_name=provider.model_name,
                    model_version=provider.model_version,
                    model_revision=provider.model_revision,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                    input_token_count=provider.input_token_count,
                    output_token_count=provider.output_token_count,
                    latency_ms=provider.latency_ms,
                    created_at=now,
                )
            )
            run.status = "SUCCEEDED"
            run.completed_at = now

    def fail(self, *, tenant_id: str, run_id: str, code: str, message: str) -> None:
        with self._factory.begin() as session:
            session.execute(
                update(GroundedExplanationRunModel)
                .where(
                    GroundedExplanationRunModel.tenant_id == UUID(tenant_id),
                    GroundedExplanationRunModel.id == UUID(run_id),
                    GroundedExplanationRunModel.status == "RUNNING",
                )
                .values(
                    status="FAILED",
                    completed_at=datetime.now(UTC),
                    failure_code=code[:128],
                    failure_message=message[:1000],
                )
            )


def _get_or_create_pack(
    session: Session,
    retrieval: PolicyRetrievalRunModel,
    now: datetime,
) -> CitationPack:
    existing = session.scalar(
        select(PolicyCitationPackModel).where(
            PolicyCitationPackModel.tenant_id == retrieval.tenant_id,
            PolicyCitationPackModel.retrieval_run_id == retrieval.id,
        )
    )
    if existing is not None:
        return _load_pack(session, retrieval.tenant_id, existing.id)
    hit_rows = session.execute(
        select(PolicyRetrievalRunHitModel, PolicyClauseModel)
        .join(
            PolicyClauseModel,
            PolicyClauseModel.id == PolicyRetrievalRunHitModel.policy_clause_row_id,
        )
        .where(
            PolicyRetrievalRunHitModel.tenant_id == retrieval.tenant_id,
            PolicyRetrievalRunHitModel.retrieval_run_id == retrieval.id,
        )
        .order_by(PolicyRetrievalRunHitModel.rank)
    ).all()
    if not hit_rows:
        raise ValidationError("A successful retrieval run must contain at least one hit.")
    citations: list[CitationSnapshot] = []
    for hit, clause in hit_rows:
        if clause.document_status != "ACTIVE" or clause.effective_from > retrieval.as_of_date:
            raise ValidationError("Citation pack contains an inactive or future policy clause.")
        if clause.effective_to is not None and clause.effective_to < retrieval.as_of_date:
            raise ValidationError("Citation pack contains an expired policy clause.")
        citations.append(
            CitationSnapshot(
                citation_id=f"CIT-{hit.rank:03d}",
                rank=hit.rank,
                policy_clause_row_id=str(clause.id),
                policy_clause_id=clause.clause_id,
                document_id=clause.document_id,
                document_version=clause.document_version,
                title=clause.title,
                section_path=tuple(clause.section_path),
                clause_type=ClauseType(clause.clause_type),
                text=clause.text,
                effective_from=clause.effective_from,
                effective_to=clause.effective_to,
                source_type=clause.source_type,
                source_hash=clause.source_hash,
                query_strategy=QueryStrategy(retrieval.strategy),
                matched_query_ids=tuple(str(value) for value in hit.matched_query_ids),
                retrieval_profile_hash=retrieval.base_retrieval_profile_hash,
            )
        )
    pack = CitationPack(
        id=str(uuid4()),
        tenant_id=str(retrieval.tenant_id),
        case_id=str(retrieval.case_id),
        retrieval_run_id=str(retrieval.id),
        retrieval_profile_hash=retrieval.base_retrieval_profile_hash,
        citations=tuple(citations),
        created_at=now,
    )
    session.add(
        PolicyCitationPackModel(
            id=UUID(pack.id),
            tenant_id=retrieval.tenant_id,
            case_id=retrieval.case_id,
            retrieval_run_id=retrieval.id,
            schema_version=pack.schema_version,
            retrieval_profile_hash=pack.retrieval_profile_hash,
            content_hash=pack.content_hash,
            created_at=now,
        )
    )
    # Flush the parent explicitly because these append-only mappers expose no
    # ORM relationship; the composite FK still protects the database boundary.
    session.flush()
    for citation in pack.citations:
        session.add(
            PolicyCitationPackItemModel(
                id=uuid4(),
                tenant_id=retrieval.tenant_id,
                citation_pack_id=UUID(pack.id),
                citation_id=citation.citation_id,
                rank=citation.rank,
                policy_clause_row_id=UUID(citation.policy_clause_row_id),
                policy_clause_id=citation.policy_clause_id,
                document_id=citation.document_id,
                document_version=citation.document_version,
                title=citation.title,
                section_path=list(citation.section_path),
                clause_type=citation.clause_type.value,
                clause_text=citation.text,
                effective_from=citation.effective_from,
                effective_to=citation.effective_to,
                source_type=citation.source_type,
                source_hash=citation.source_hash,
                retrieval_mode=citation.retrieval_mode,
                query_strategy=citation.query_strategy.value,
                matched_query_ids=list(citation.matched_query_ids),
                retrieval_profile_hash=citation.retrieval_profile_hash,
                created_at=now,
            )
        )
    session.flush()
    return pack


def _load_pack(session: Session, tenant_id: UUID, pack_id: UUID) -> CitationPack:
    pack = session.scalar(
        select(PolicyCitationPackModel).where(
            PolicyCitationPackModel.tenant_id == tenant_id,
            PolicyCitationPackModel.id == pack_id,
        )
    )
    assert pack is not None
    items = session.scalars(
        select(PolicyCitationPackItemModel)
        .where(
            PolicyCitationPackItemModel.tenant_id == tenant_id,
            PolicyCitationPackItemModel.citation_pack_id == pack_id,
        )
        .order_by(PolicyCitationPackItemModel.rank)
    ).all()
    result = CitationPack(
        id=str(pack.id),
        tenant_id=str(pack.tenant_id),
        case_id=str(pack.case_id),
        retrieval_run_id=str(pack.retrieval_run_id),
        retrieval_profile_hash=pack.retrieval_profile_hash,
        citations=tuple(
            CitationSnapshot(
                citation_id=item.citation_id,
                rank=item.rank,
                policy_clause_row_id=str(item.policy_clause_row_id),
                policy_clause_id=item.policy_clause_id,
                document_id=item.document_id,
                document_version=item.document_version,
                title=item.title,
                section_path=tuple(item.section_path),
                clause_type=ClauseType(item.clause_type),
                text=item.clause_text,
                effective_from=item.effective_from,
                effective_to=item.effective_to,
                source_type=item.source_type,
                source_hash=item.source_hash,
                retrieval_mode="HYBRID",
                query_strategy=QueryStrategy(item.query_strategy),
                matched_query_ids=tuple(str(value) for value in item.matched_query_ids),
                retrieval_profile_hash=item.retrieval_profile_hash,
            )
            for item in items
        ),
        created_at=pack.created_at,
    )
    if result.content_hash != pack.content_hash:
        raise ValidationError("The immutable citation pack content hash does not match.")
    return result


def _ensure_profile(
    session: Session,
    *,
    provider: ProviderExecutionMetadata,
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
) -> GroundingProfileModel:
    version = f"1.0.0-{provider.provider_name}"
    profile_id = uuid5(_NAMESPACE, f"grounding:{version}:{prompt_hash}:{provider.model_revision}")
    row = session.get(GroundingProfileModel, profile_id)
    if row is not None:
        return row
    values = {
        "provider_name": provider.provider_name,
        "model_artifact": provider.model_name,
        "model_revision": provider.model_revision,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "validator_name": "citation_allowlist_validator",
        "validator_version": "1.0.0",
    }
    row = GroundingProfileModel(
        id=profile_id,
        profile_name="grounded_policy_explanation",
        profile_version=version,
        profile_hash=stable_json_hash(values),
        created_at=datetime.now(UTC),
        **values,
    )
    session.add(row)
    session.flush()
    return row


def _to_run(row: GroundedExplanationRunModel) -> GroundedExplanationRun:
    return GroundedExplanationRun(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        case_id=str(row.case_id),
        retrieval_run_id=str(row.retrieval_run_id),
        citation_pack_id=str(row.citation_pack_id),
        status=GroundedExplanationRunStatus(row.status),
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
    )


__all__ = ["SQLAlchemyGroundedExplanationRunRepository"]
