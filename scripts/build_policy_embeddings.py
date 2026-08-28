"""Build append-only Qwen clause embeddings and activate one index per tenant."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select, update

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyDocumentModel,
    PolicyEmbeddingProfileModel,
    PolicyIndexVersionModel,
    TenantModel,
)
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.adapters.persistence.session import create_session_factory, session_scope
from app.adapters.retrieval.embedding_http import HTTPEmbeddingProvider
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingVector,
    PolicyClauseRecord,
    PolicyIndexStatus,
    serialize_policy_clause,
)

MODEL_ARTIFACT = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QUERY_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
TEMPLATE_CONTRACT = (
    "문서: {title}\n섹션: {section_path}\n정책 유형: {policy_type}\n"
    "조항 유형: {clause_type}\n본문: {text}"
)
PROFILE_ID = uuid5(NAMESPACE_URL, "urn:csight:policy-embedding-profile:qwen3-0.6b:1.0.0")
INDEX_NAME = "csight_policy_reference"
INDEX_VERSION = "1.0.0"
REFERENCE_TENANTS = ("csight-demo-brand", "csight-demo-retail")
REFERENCE_CORPUS_NAME = "csight_synthetic_policy_reference"
REFERENCE_CORPUS_VERSION = "1.0.0"
REFERENCE_CORPUS_HASH = "8e60f4ce869ba83288ac094ba09465481a9d2e431cfe45a7ac4de4114092c237"


@dataclass(frozen=True, slots=True)
class CorpusIndexMetadata:
    name: str
    version: str
    source_hash: str
    document_count: int | None = None
    clause_count: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingBuildSummary:
    total: int
    reused: int
    created: int
    tenant_count: int
    truncation_count: int
    token_min: int
    token_p50: float
    token_max: int


@dataclass(frozen=True, slots=True)
class PersistedEmbeddingSnapshot:
    policy_clause_row_id: UUID
    document_text_hash: str
    embedding_dimension: int
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PersistedIndexSnapshot:
    index_name: str
    index_version: str
    corpus_name: str
    corpus_version: str
    corpus_source_hash: str
    lexical_profile_name: str
    lexical_profile_version: str
    lexical_k1: float
    lexical_b: float
    embedding_profile_id: UUID
    fusion_profile_name: str
    fusion_profile_version: str
    fusion_rrf_k: int
    fusion_lexical_weight: float
    fusion_dense_weight: float
    status: str
    expected_clause_count: int
    indexed_clause_count: int
    activated_at: datetime | None
    retired_at: datetime | None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding_snapshot(row: PolicyClauseEmbeddingModel) -> PersistedEmbeddingSnapshot:
    return PersistedEmbeddingSnapshot(
        policy_clause_row_id=row.policy_clause_row_id,
        document_text_hash=row.document_text_hash,
        embedding_dimension=row.embedding_dimension,
        embedding=tuple(row.embedding),
    )


def index_snapshot(row: PolicyIndexVersionModel) -> PersistedIndexSnapshot:
    return PersistedIndexSnapshot(
        index_name=row.index_name,
        index_version=row.index_version,
        corpus_name=row.corpus_name,
        corpus_version=row.corpus_version,
        corpus_source_hash=row.corpus_source_hash,
        lexical_profile_name=row.lexical_profile_name,
        lexical_profile_version=row.lexical_profile_version,
        lexical_k1=row.lexical_k1,
        lexical_b=row.lexical_b,
        embedding_profile_id=row.embedding_profile_id,
        fusion_profile_name=row.fusion_profile_name,
        fusion_profile_version=row.fusion_profile_version,
        fusion_rrf_k=row.fusion_rrf_k,
        fusion_lexical_weight=row.fusion_lexical_weight,
        fusion_dense_weight=row.fusion_dense_weight,
        status=row.status,
        expected_clause_count=row.expected_clause_count,
        indexed_clause_count=row.indexed_clause_count,
        activated_at=row.activated_at,
        retired_at=row.retired_at,
    )


def validate_persisted_embedding_integrity(
    clauses: Sequence[PolicyClauseRecord],
    embeddings: Sequence[PersistedEmbeddingSnapshot],
    *,
    require_complete: bool,
) -> None:
    """Validate that reusable rows still represent the current passage contract."""

    expected_hashes = {clause.row_id: _hash(serialize_policy_clause(clause)) for clause in clauses}
    seen: set[str] = set()
    for row in embeddings:
        row_id = str(row.policy_clause_row_id)
        expected_hash = expected_hashes.get(row_id)
        if expected_hash is None or row_id in seen:
            raise ValueError("persisted policy embedding clause identity mismatch")
        seen.add(row_id)
        try:
            vector = tuple(float(value) for value in row.embedding)
        except (TypeError, ValueError):
            raise ValueError("persisted policy embedding vector is invalid") from None
        if row.document_text_hash != expected_hash:
            raise ValueError("persisted policy embedding document text hash mismatch")
        if row.embedding_dimension != 1024 or len(vector) != 1024:
            raise ValueError("persisted policy embedding dimension mismatch")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("persisted policy embedding contains NaN or infinity")
    if require_complete and seen != set(expected_hashes):
        raise ValueError("persisted policy embedding set is incomplete")


def validate_protected_index_state(
    index: PersistedIndexSnapshot,
    *,
    metadata: CorpusIndexMetadata,
    expected_clause_count: int,
    index_name: str = INDEX_NAME,
    index_version: str = INDEX_VERSION,
) -> None:
    """Require an existing protected index to be the exact clean ACTIVE snapshot."""

    if (
        index.index_name != index_name
        or index.index_version != index_version
        or index.corpus_name != metadata.name
        or index.corpus_version != metadata.version
        or index.corpus_source_hash != metadata.source_hash
        or index.lexical_profile_name != "ko_policy_lexical"
        or index.lexical_profile_version != "1.0.0"
        or index.lexical_k1 != 1.2
        or index.lexical_b != 0.75
        or index.embedding_profile_id != PROFILE_ID
        or index.fusion_profile_name != "policy_rrf"
        or index.fusion_profile_version != "1.0.0"
        or index.fusion_rrf_k != 20
        or index.fusion_lexical_weight != 1.5
        or index.fusion_dense_weight != 0.5
        or index.expected_clause_count != expected_clause_count
    ):
        raise ValueError("protected target policy index metadata mismatch")
    if (
        index.status != PolicyIndexStatus.ACTIVE.value
        or index.indexed_clause_count != expected_clause_count
        or index.activated_at is None
        or index.retired_at is not None
    ):
        raise ValueError("protected target policy index is not a clean ACTIVE snapshot")


def load_single_tenant_manifest(path: Path) -> CorpusIndexMetadata:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("policy corpus manifest must be an object")
    if payload.get("source_type") != "SYNTHETIC_REFERENCE":
        raise ValueError("target policy corpus must remain SYNTHETIC_REFERENCE")
    if payload.get("tenant_count") != 1:
        raise ValueError("target policy corpus manifest must contain exactly one tenant")
    source_hash = payload.get("source_hash")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        raise ValueError("target policy corpus source hash is invalid")
    document_count = payload.get("document_count")
    clause_count = payload.get("clause_count")
    if not isinstance(document_count, int) or document_count <= 0:
        raise ValueError("target policy corpus document count is invalid")
    if not isinstance(clause_count, int) or clause_count <= 0:
        raise ValueError("target policy corpus clause count is invalid")
    return CorpusIndexMetadata(
        name=str(payload["corpus_name"]),
        version=str(payload["corpus_version"]),
        source_hash=source_hash,
        document_count=document_count,
        clause_count=clause_count,
    )


def _profile() -> DenseProfile:
    return DenseProfile(
        model_artifact=MODEL_ARTIFACT,
        model_revision=MODEL_REVISION,
        embedding_dimension=1024,
        pooling_strategy="last-token",
        normalize_embeddings=True,
        query_instruction=QUERY_INSTRUCTION,
        max_query_tokens=8192,
        max_document_tokens=8192,
    )


def build_policy_embeddings(
    *,
    settings: Settings,
    embedding_base_url: str,
    batch_size: int,
    tenant_slug: str | None = None,
    corpus_manifest: Path | None = None,
    protect_existing_index: bool = False,
    index_name: str = INDEX_NAME,
    index_version: str = INDEX_VERSION,
) -> EmbeddingBuildSummary:
    """Build embeddings for the frozen reference tenants or one explicit synthetic tenant."""

    if not 1 <= batch_size <= 32:
        raise ValueError("batch size must be between 1 and 32")
    if (tenant_slug is None) != (corpus_manifest is None):
        raise ValueError("tenant and corpus manifest must be provided together")
    if not index_name.strip() or not index_version.strip():
        raise ValueError("policy index name and version must be non-empty")
    if settings.environment.strip().lower() not in {"local", "test"}:
        raise ValueError("synthetic policy embeddings are allowed only in local or test")
    metadata = (
        load_single_tenant_manifest(corpus_manifest)
        if corpus_manifest is not None
        else CorpusIndexMetadata(
            name=REFERENCE_CORPUS_NAME,
            version=REFERENCE_CORPUS_VERSION,
            source_hash=REFERENCE_CORPUS_HASH,
        )
    )
    target_slugs = (tenant_slug,) if tenant_slug is not None else REFERENCE_TENANTS
    factory = create_session_factory(get_engine(settings))
    profile = _profile()
    with factory() as session:
        tenants = tuple(
            session.scalars(
                select(TenantModel)
                .where(TenantModel.slug.in_(target_slugs))
                .order_by(TenantModel.slug)
            )
        )
        if {tenant.slug for tenant in tenants} != set(target_slugs):
            raise ValueError("policy embedding target tenant is missing")
        if any(not tenant.is_active for tenant in tenants):
            raise ValueError("policy embedding target tenant is inactive")
        tenant_ids = tuple(tenant.id for tenant in tenants)
        clauses = tuple(
            to_policy_clause_record(row)
            for row in session.scalars(
                select(PolicyClauseModel)
                .where(PolicyClauseModel.tenant_id.in_(tenant_ids))
                .order_by(
                    PolicyClauseModel.tenant_id,
                    PolicyClauseModel.document_id,
                    PolicyClauseModel.document_version,
                    PolicyClauseModel.clause_id,
                )
            )
        )
        if not clauses:
            raise ValueError("policy embedding target has no clauses")
        if metadata.clause_count is not None and len(clauses) != metadata.clause_count:
            raise ValueError("policy corpus clause count differs from target manifest")
        if metadata.document_count is not None:
            document_count = session.scalar(
                select(func.count(PolicyDocumentModel.id)).where(
                    PolicyDocumentModel.tenant_id.in_(tenant_ids)
                )
            )
            if document_count != metadata.document_count:
                raise ValueError("policy corpus document count differs from target manifest")
        existing_embeddings = tuple(
            session.scalars(
                select(PolicyClauseEmbeddingModel).where(
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                    PolicyClauseEmbeddingModel.tenant_id.in_(tenant_ids),
                )
            )
        )
        existing_indexes: tuple[PolicyIndexVersionModel, ...] = ()
        if protect_existing_index:
            existing_indexes = tuple(
                session.scalars(
                    select(PolicyIndexVersionModel).where(
                        PolicyIndexVersionModel.tenant_id.in_(tenant_ids)
                    )
                )
            )
            expected_ids = {
                uuid5(
                    NAMESPACE_URL,
                    f"urn:csight:policy-index:{tenant.id}:{index_name}:{index_version}",
                )
                for tenant in tenants
            }
            if any(index.id not in expected_ids for index in existing_indexes):
                raise ValueError("protected target has an unrelated policy index")
            if len(existing_indexes) > len(tenants):
                raise ValueError("protected target has duplicate policy indexes")
            for index in existing_indexes:
                tenant_clause_count = sum(
                    clause.tenant_id == str(index.tenant_id) for clause in clauses
                )
                validate_protected_index_state(
                    index_snapshot(index),
                    metadata=metadata,
                    expected_clause_count=tenant_clause_count,
                    index_name=index_name,
                    index_version=index_version,
                )
            validate_persisted_embedding_integrity(
                clauses,
                tuple(embedding_snapshot(row) for row in existing_embeddings),
                require_complete=bool(existing_indexes),
            )
    existing_row_ids = {str(embedding.policy_clause_row_id) for embedding in existing_embeddings}
    pending = tuple(clause for clause in clauses if clause.row_id not in existing_row_ids)
    provider = HTTPEmbeddingProvider(base_url=embedding_base_url, timeout_seconds=180)
    embedded: list[tuple[PolicyClauseRecord, EmbeddingVector, str]] = []
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        texts = tuple(serialize_policy_clause(clause) for clause in batch)
        vectors = provider.embed_documents(texts, profile)
        embedded.extend(
            (clause, vector, _hash(text))
            for clause, vector, text in zip(batch, vectors, texts, strict=True)
        )
    now = datetime.now(UTC)
    with session_scope(factory) as session:
        stored_profile = session.get(PolicyEmbeddingProfileModel, PROFILE_ID)
        if stored_profile is None:
            session.add(
                PolicyEmbeddingProfileModel(
                    id=PROFILE_ID,
                    profile_name=profile.name,
                    profile_version=profile.version,
                    provider_name=profile.provider_name,
                    model_artifact=profile.model_artifact,
                    model_revision=profile.model_revision,
                    embedding_dimension=profile.embedding_dimension,
                    pooling_strategy=profile.pooling_strategy,
                    normalize_embeddings=profile.normalize_embeddings,
                    query_instruction=profile.query_instruction,
                    query_instruction_hash=_hash(profile.query_instruction),
                    document_template_name=profile.document_template_name,
                    document_template_version=profile.document_template_version,
                    document_template_hash=_hash(TEMPLATE_CONTRACT),
                    max_query_tokens=profile.max_query_tokens,
                    max_document_tokens=profile.max_document_tokens,
                )
            )
        elif (
            stored_profile.model_revision != MODEL_REVISION
            or stored_profile.embedding_dimension != 1024
            or stored_profile.query_instruction_hash != _hash(profile.query_instruction)
            or stored_profile.document_template_hash != _hash(TEMPLATE_CONTRACT)
        ):
            raise ValueError("immutable embedding profile content mismatch")
        session.flush()
        for clause, vector, text_hash in embedded:
            session.add(
                PolicyClauseEmbeddingModel(
                    id=uuid5(
                        NAMESPACE_URL, f"urn:csight:policy-embedding:{clause.row_id}:{PROFILE_ID}"
                    ),
                    tenant_id=UUID(clause.tenant_id),
                    policy_clause_row_id=UUID(clause.row_id),
                    embedding_profile_id=PROFILE_ID,
                    embedding=list(vector.values),
                    embedding_dimension=vector.dimension,
                    document_text_hash=text_hash,
                )
            )
        session.flush()
        persisted_embeddings = tuple(
            session.scalars(
                select(PolicyClauseEmbeddingModel).where(
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                    PolicyClauseEmbeddingModel.tenant_id.in_(tenant_ids),
                )
            )
        )
        validate_persisted_embedding_integrity(
            clauses,
            tuple(embedding_snapshot(row) for row in persisted_embeddings),
            require_complete=True,
        )
        tenant_counts = session.execute(
            select(PolicyClauseModel.tenant_id, func.count(PolicyClauseModel.id))
            .where(PolicyClauseModel.tenant_id.in_(tenant_ids))
            .group_by(PolicyClauseModel.tenant_id)
        ).all()
        for tenant_id, count in tenant_counts:
            index_id = uuid5(
                NAMESPACE_URL,
                f"urn:csight:policy-index:{tenant_id}:{index_name}:{index_version}",
            )
            index = session.get(PolicyIndexVersionModel, index_id)
            created_index = index is None
            if index is None:
                index = PolicyIndexVersionModel(
                    id=index_id,
                    tenant_id=tenant_id,
                    index_name=index_name,
                    index_version=index_version,
                    corpus_name=metadata.name,
                    corpus_version=metadata.version,
                    corpus_source_hash=metadata.source_hash,
                    lexical_profile_name="ko_policy_lexical",
                    lexical_profile_version="1.0.0",
                    lexical_k1=1.2,
                    lexical_b=0.75,
                    embedding_profile_id=PROFILE_ID,
                    fusion_profile_name="policy_rrf",
                    fusion_profile_version="1.0.0",
                    fusion_rrf_k=20,
                    fusion_lexical_weight=1.5,
                    fusion_dense_weight=0.5,
                    status=PolicyIndexStatus.BUILDING.value,
                    expected_clause_count=count,
                    indexed_clause_count=0,
                    activated_at=None,
                    retired_at=None,
                )
                session.add(index)
                session.flush()
            elif protect_existing_index:
                validate_protected_index_state(
                    index_snapshot(index),
                    metadata=metadata,
                    expected_clause_count=count,
                    index_name=index_name,
                    index_version=index_version,
                )
            elif (
                index.corpus_name != metadata.name
                or index.corpus_version != metadata.version
                or index.corpus_source_hash != metadata.source_hash
                or index.embedding_profile_id != PROFILE_ID
                or index.expected_clause_count != count
            ):
                raise ValueError("immutable policy index content mismatch")
            embedded_count = session.scalar(
                select(func.count(PolicyClauseEmbeddingModel.id)).where(
                    PolicyClauseEmbeddingModel.tenant_id == tenant_id,
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                )
            )
            if embedded_count != count:
                raise ValueError("policy index embedding count mismatch")
            if created_index:
                if protect_existing_index:
                    conflicting_active = session.scalar(
                        select(func.count(PolicyIndexVersionModel.id)).where(
                            PolicyIndexVersionModel.tenant_id == tenant_id,
                            PolicyIndexVersionModel.index_name == index_name,
                            PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                            PolicyIndexVersionModel.id != index_id,
                        )
                    )
                    if conflicting_active:
                        raise ValueError("protected target has another active policy index")
                else:
                    session.execute(
                        update(PolicyIndexVersionModel)
                        .where(
                            PolicyIndexVersionModel.tenant_id == tenant_id,
                            PolicyIndexVersionModel.index_name == index_name,
                            PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                            PolicyIndexVersionModel.id != index_id,
                        )
                        .values(status=PolicyIndexStatus.RETIRED.value, retired_at=now)
                    )
                index.status = PolicyIndexStatus.ACTIVE.value
                index.indexed_clause_count = count
                index.activated_at = now
            elif index.status != PolicyIndexStatus.ACTIVE.value:
                if not protect_existing_index:
                    session.execute(
                        update(PolicyIndexVersionModel)
                        .where(
                            PolicyIndexVersionModel.tenant_id == tenant_id,
                            PolicyIndexVersionModel.index_name == index_name,
                            PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                            PolicyIndexVersionModel.id != index_id,
                        )
                        .values(status=PolicyIndexStatus.RETIRED.value, retired_at=now)
                    )
                    index.status = PolicyIndexStatus.ACTIVE.value
                    index.indexed_clause_count = count
                    index.activated_at = now
    token_counts = [vector.token_count or 0 for _, vector, _ in embedded]
    return EmbeddingBuildSummary(
        total=len(clauses),
        reused=len(clauses) - len(pending),
        created=len(pending),
        tenant_count=len(tenants),
        truncation_count=sum(vector.truncated for _, vector, _ in embedded),
        token_min=min(token_counts, default=0),
        token_p50=float(statistics.median(token_counts)) if token_counts else 0.0,
        token_max=max(token_counts, default=0),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--tenant")
    parser.add_argument("--corpus-manifest", type=Path)
    parser.add_argument("--protect-existing-index", action="store_true")
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    try:
        summary = build_policy_embeddings(
            settings=settings,
            embedding_base_url=arguments.embedding_base_url,
            batch_size=arguments.batch_size,
            tenant_slug=arguments.tenant,
            corpus_manifest=arguments.corpus_manifest,
            protect_existing_index=arguments.protect_existing_index,
        )
    except Exception as error:
        print(f"POLICY_EMBEDDINGS_FAILED code={getattr(error, 'code', type(error).__name__)}")
        return 1
    print(
        "POLICY_EMBEDDINGS_BUILT "
        f"total={summary.total} reused={summary.reused} created={summary.created} "
        f"tenants={summary.tenant_count} dimension=1024 "
        f"truncation_count={summary.truncation_count} "
        f"token_min={summary.token_min} token_p50={summary.token_p50:g} "
        f"token_max={summary.token_max}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
