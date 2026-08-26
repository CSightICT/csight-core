"""Manifest-driven, transactional policy corpus ingestion adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.persistence.models import (
    PolicyClauseModel,
    PolicyDocumentModel,
    PolicyIngestionRunModel,
    TenantModel,
)
from app.platform.policy_reference import PolicyClause, PolicyDocument
from app.platform.policy_retrieval import (
    PolicyDocumentVersionContentMismatchError,
    PolicyIngestionStatus,
)


@dataclass(frozen=True, slots=True)
class PolicyIngestionOutcome:
    run_id: UUID
    reused: bool
    document_count: int
    clause_count: int


def ingest_validated_policy_corpus(
    *, session: Session, corpus_root: Path, allow_synthetic_tenant_creation: bool
) -> PolicyIngestionOutcome:
    manifest_path = corpus_root / "manifests" / "policy_corpus_v1.json"
    documents_path = corpus_root / "normalized" / "policy_documents_v1.jsonl"
    clauses_path = corpus_root / "clauses" / "policy_clauses_v1.jsonl"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("policy corpus manifest must be an object")
    documents = tuple(
        PolicyDocument.model_validate(json.loads(line))
        for line in documents_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    clauses = tuple(
        PolicyClause.model_validate(json.loads(line))
        for line in clauses_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    corpus_hash = hashlib.sha256(
        "".join(document.source_hash for document in documents).encode("utf-8")
    ).hexdigest()
    if corpus_hash != manifest.get("source_hash"):
        raise ValueError("policy corpus source hash does not match manifest")
    if len(documents) != manifest.get("document_count") or len(clauses) != manifest.get(
        "clause_count"
    ):
        raise ValueError("policy corpus counts do not match manifest")
    existing = session.scalar(
        select(PolicyIngestionRunModel).where(
            PolicyIngestionRunModel.corpus_source_hash == corpus_hash,
            PolicyIngestionRunModel.manifest_hash == manifest_hash,
            PolicyIngestionRunModel.builder_version == str(manifest["builder_version"]),
            PolicyIngestionRunModel.status == PolicyIngestionStatus.SUCCEEDED.value,
        )
    )
    if existing is not None:
        return PolicyIngestionOutcome(
            run_id=existing.id,
            reused=True,
            document_count=existing.ingested_document_count,
            clause_count=existing.ingested_clause_count,
        )
    run_id = uuid4()
    now = datetime.now(UTC)
    run = PolicyIngestionRunModel(
        id=run_id,
        corpus_name=str(manifest["corpus_name"]),
        corpus_version=str(manifest["corpus_version"]),
        corpus_source_hash=corpus_hash,
        manifest_hash=manifest_hash,
        status=PolicyIngestionStatus.RUNNING.value,
        started_at=now,
        completed_at=None,
        expected_document_count=len(documents),
        ingested_document_count=0,
        expected_clause_count=len(clauses),
        ingested_clause_count=0,
        builder_version=str(manifest["builder_version"]),
        schema_version=str(manifest["schema_version"]),
        failure_code=None,
        failure_message=None,
    )
    session.add(run)
    session.flush()
    try:
        tenant_ids = _resolve_tenants(
            session,
            tenant_slugs=frozenset(document.tenant_id for document in documents),
            allow_creation=allow_synthetic_tenant_creation,
        )
        document_rows = ingest_policy_documents(
            session, run_id=run_id, documents=documents, tenant_ids=tenant_ids
        )
        _ingest_clauses(
            session,
            run_id=run_id,
            clauses=clauses,
            tenant_ids=tenant_ids,
            document_rows=document_rows,
        )
        run.ingested_document_count = len(documents)
        run.ingested_clause_count = len(clauses)
        run.status = PolicyIngestionStatus.SUCCEEDED.value
        run.completed_at = datetime.now(UTC)
        session.flush()
    except Exception:
        raise
    return PolicyIngestionOutcome(
        run_id=run_id,
        reused=False,
        document_count=len(documents),
        clause_count=len(clauses),
    )


def _resolve_tenants(
    session: Session, *, tenant_slugs: frozenset[str], allow_creation: bool
) -> dict[str, UUID]:
    rows = tuple(session.scalars(select(TenantModel).where(TenantModel.slug.in_(tenant_slugs))))
    by_slug = {row.slug: row.id for row in rows}
    missing = tenant_slugs - by_slug.keys()
    if missing and not allow_creation:
        raise ValueError("policy corpus tenant mappings are missing")
    for slug in sorted(missing):
        tenant_id = uuid5(NAMESPACE_URL, f"urn:csight:synthetic-policy-tenant:{slug}")
        session.add(
            TenantModel(
                id=tenant_id,
                slug=slug,
                name=f"CSight Synthetic Policy {slug}",
                is_active=True,
            )
        )
        by_slug[slug] = tenant_id
    session.flush()
    return by_slug


def ingest_policy_documents(
    session: Session,
    *,
    run_id: UUID,
    documents: tuple[PolicyDocument, ...],
    tenant_ids: dict[str, UUID],
) -> dict[tuple[str, str, str], PolicyDocumentModel]:
    result: dict[tuple[str, str, str], PolicyDocumentModel] = {}
    for document in documents:
        tenant_id = tenant_ids[document.tenant_id]
        key = (document.tenant_id, document.document_id, document.document_version)
        existing = session.scalar(
            select(PolicyDocumentModel).where(
                PolicyDocumentModel.tenant_id == tenant_id,
                PolicyDocumentModel.document_id == document.document_id,
                PolicyDocumentModel.document_version == document.document_version,
            )
        )
        if existing is not None:
            if existing.source_hash != document.source_hash:
                raise PolicyDocumentVersionContentMismatchError()
            result[key] = existing
            continue
        supersedes = _split_version_reference(document.supersedes)
        superseded_by = _split_version_reference(document.superseded_by)
        row = PolicyDocumentModel(
            id=uuid5(
                NAMESPACE_URL,
                f"urn:csight:policy-document:{tenant_id}:{document.document_id}:{document.document_version}",
            ),
            tenant_id=tenant_id,
            document_id=document.document_id,
            document_version=document.document_version,
            title=document.title,
            policy_type=document.policy_type,
            authority_level=document.authority_level,
            product_categories=list(document.product_categories),
            effective_from=document.effective_from,
            effective_to=document.effective_to,
            document_status=document.status.value,
            source_type=document.source_type,
            source_hash=document.source_hash,
            supersedes_document_id=supersedes[0],
            supersedes_document_version=supersedes[1],
            superseded_by_document_id=superseded_by[0],
            superseded_by_document_version=superseded_by[1],
            ingestion_run_id=run_id,
        )
        session.add(row)
        result[key] = row
    session.flush()
    return result


def _ingest_clauses(
    session: Session,
    *,
    run_id: UUID,
    clauses: tuple[PolicyClause, ...],
    tenant_ids: dict[str, UUID],
    document_rows: dict[tuple[str, str, str], PolicyDocumentModel],
) -> None:
    clause_ids = {(item.tenant_id, item.clause_id) for item in clauses}
    for clause in clauses:
        if (
            clause.parent_clause_id
            and (clause.tenant_id, clause.parent_clause_id) not in clause_ids
        ):
            raise ValueError("policy clause parent is missing or cross-tenant")
        tenant_id = tenant_ids[clause.tenant_id]
        existing = session.scalar(
            select(PolicyClauseModel).where(
                PolicyClauseModel.tenant_id == tenant_id,
                PolicyClauseModel.document_id == clause.document_id,
                PolicyClauseModel.document_version == clause.document_version,
                PolicyClauseModel.clause_id == clause.clause_id,
            )
        )
        if existing is not None:
            if (
                existing.content_hash != clause.content_hash
                or existing.source_hash != clause.source_hash
            ):
                raise PolicyDocumentVersionContentMismatchError()
            continue
        document = document_rows[(clause.tenant_id, clause.document_id, clause.document_version)]
        session.add(
            PolicyClauseModel(
                id=uuid5(
                    NAMESPACE_URL,
                    f"urn:csight:policy-clause:{tenant_id}:{clause.clause_id}",
                ),
                tenant_id=tenant_id,
                document_row_id=document.id,
                document_id=clause.document_id,
                document_version=clause.document_version,
                title=document.title,
                clause_id=clause.clause_id,
                section_path=list(clause.section_path),
                clause_type=clause.clause_type.value,
                text=clause.text,
                parent_clause_id=clause.parent_clause_id,
                policy_type=clause.policy_type,
                product_categories=list(clause.product_categories),
                defect_types=list(clause.defect_types),
                actions=list(clause.actions),
                requires_human_review=clause.requires_human_review,
                effective_from=clause.effective_from,
                effective_to=clause.effective_to,
                document_status=clause.document_status.value,
                source_type=clause.source_type,
                source_hash=clause.source_hash,
                content_hash=clause.content_hash,
                ingestion_run_id=run_id,
            )
        )
    session.flush()


def _split_version_reference(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    document_id, separator, version = value.partition("@")
    if not separator or not document_id or not version:
        raise ValueError("invalid policy document version reference")
    return document_id, version


__all__ = [
    "PolicyIngestionOutcome",
    "ingest_policy_documents",
    "ingest_validated_policy_corpus",
]
