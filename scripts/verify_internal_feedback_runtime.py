"""Explicit synthetic provider probe from the deployed Core worker environment.

No DB writes, user login, production decisions, or raw model output are emitted.
Run explicitly with --synthetic-real-models; never part of the default suite.
"""

import argparse
import json
from datetime import UTC, date, datetime
from io import BytesIO

from PIL import Image, ImageDraw
from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import TenantModel
from app.adapters.persistence.policy_repositories import (
    SQLAlchemyDenseRetriever,
    SQLAlchemyPolicyClauseRepository,
    SQLAlchemyPolicyProfileRepository,
)
from app.adapters.persistence.session import create_session_factory
from app.adapters.retrieval import (
    ExactBM25Retriever,
    HTTPEmbeddingProvider,
    ReciprocalRankFusionRetriever,
)
from app.bootstrap.dependencies import build_llm_provider, build_vision_provider
from app.bootstrap.settings import Settings
from app.bootstrap.sprint2 import _v2_prompt  # pyright: ignore[reportPrivateUsage]
from app.bootstrap.sprint4c3a import _grounding_prompt  # pyright: ignore[reportPrivateUsage]
from app.platform.analysis import VisionAnalysisRequest
from app.platform.analysis.llm_v2 import LLMTextExtractionRequestV2
from app.platform.grounding import (
    CitationPack,
    CitationSnapshot,
    GroundedExplanationInput,
    validate_grounded_explanation,
)
from app.platform.model_activation import ModelReleaseTask
from app.platform.policy_reference import ClauseType
from app.platform.policy_retrieval import DenseProfile, PolicySearchQuery, stable_json_hash
from app.platform.query_builder import QueryStrategy


def synthetic_rag_pack(settings: Settings) -> tuple[CitationPack, dict[str, object]]:
    """Read-only maintenance probe of the existing synthetic tenant's actual retrieval adapters.

    Does not log in or impersonate a user. No HTTP authentication/end-to-end claim is made.
    """
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        tenant = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == "csight-demo-brand")
        )
    assert tenant is not None
    query = PolicySearchQuery(
        tenant_id=str(tenant),
        query="용기 파손 교환 사진 주문번호",
        as_of_date=date(2026, 9, 10),
        top_k=3,
    )
    profile = SQLAlchemyPolicyProfileRepository(factory).get_active_profile(str(tenant))
    candidates = SQLAlchemyPolicyClauseRepository(factory).candidates(query)
    assert candidates and all(c.source_type == "SYNTHETIC_REFERENCE" for c in candidates)
    lexical = ExactBM25Retriever().retrieve(
        query=query, candidates=candidates, profile=profile.lexical
    )
    assert settings.embedding_base_url is not None
    vector = HTTPEmbeddingProvider(base_url=str(settings.embedding_base_url)).embed_query(
        query.query, profile.dense
    )
    dense = SQLAlchemyDenseRetriever(factory).retrieve(
        query=query, query_vector=vector, embedding_profile_id=profile.embedding_profile_id
    )
    hits = ReciprocalRankFusionRetriever().fuse(
        lexical_hits=lexical, dense_hits=dense, profile=profile.fusion, top_k=3
    )
    assert len(hits) == 3 and all(hit.clause.tenant_id == str(tenant) for hit in hits)
    profile_hash = stable_json_hash(profile.model_dump(mode="json"))
    pack = CitationPack(
        id="synthetic-rag-probe",
        tenant_id=str(tenant),
        case_id="synthetic",
        retrieval_run_id="synthetic-read-only",
        retrieval_profile_hash=profile_hash,
        created_at=datetime.now(UTC),
        citations=tuple(
            CitationSnapshot(
                citation_id=f"CIT-{rank:03d}",
                rank=rank,
                policy_clause_row_id=hit.clause.row_id,
                policy_clause_id=hit.clause.clause_id,
                document_id=hit.clause.document_id,
                document_version=hit.clause.document_version,
                title=hit.clause.title,
                section_path=hit.clause.section_path,
                clause_type=ClauseType(hit.clause.clause_type.value),
                text=hit.clause.text,
                effective_from=hit.clause.effective_from,
                effective_to=hit.clause.effective_to,
                source_type=hit.clause.source_type,
                source_hash=hit.clause.source_hash,
                query_strategy=QueryStrategy.RAW,
                matched_query_ids=("Q1",),
                retrieval_profile_hash=profile_hash,
            )
            for rank, hit in enumerate(hits, 1)
        ),
    )
    return pack, {
        "status": "PASS",
        "scope": "READ_ONLY_SYNTHETIC_ADAPTER_CHAIN",
        "top_k": 3,
        "lexical_hits": len(lexical),
        "dense_hits": len(dense),
        "same_tenant": True,
        "index_version": profile.index_version,
        "profile_hash": profile_hash,
        "reranker_called": False,
        "query_builder_called": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-real-models", action="store_true", required=True)
    parser.add_argument("--with-synthetic-rag", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    assert settings.shadow_human_feedback_enabled and settings.environment == "local"
    assert settings.llm_provider == "llama_cpp" and settings.vision_provider == "remote"
    report: dict[str, object] = {
        "observed_at": datetime.now(UTC).isoformat(),
        "scope": "DEPLOYED_WORKER_REAL_PROVIDERS_SYNTHETIC_ONLY",
        "database_writes": 0,
        "business_effects": 0,
        "passwords_used": False,
        "full_authenticated_workflow": "NOT_RUN",
        "qualification": False,
    }
    phase = "extraction"
    try:
        llm = build_llm_provider(settings)
        request = LLMTextExtractionRequestV2(
            customer_message="합성 문의입니다. 용기 하단이 깨져 있습니다. 교환해주세요.",
            order_ref="SYNTHETIC-INTERNAL-ONLY",
            product_ref="SYNTHETIC-PUMP",
        )
        result = llm.extract_text_v2(request, _v2_prompt(settings))
        assert result.result.claims and result.result.requested_actions
        result.result.require_exact_source_quotes(
            customer_message=request.customer_message, provider="llama_cpp"
        )
        report[phase] = {
            "status": "PASS",
            "provider": result.metadata.provider_name,
            "model_revision": result.metadata.model_revision,
            "prompt_version": _v2_prompt(settings).version,
            "claims": len(result.result.claims),
            "exact_quotes": True,
            "latency_ms": result.metadata.latency_ms,
        }
        phase = "vision"
        image = Image.new("RGB", (256, 256), color=(242, 246, 248))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((72, 74, 184, 226), radius=16, fill=(217, 224, 229))
        draw.line(((134, 74), (120, 104), (145, 128), (124, 158)), fill=(183, 48, 48), width=5)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        vision = build_vision_provider(settings)
        assessment = vision.analyze_image(
            VisionAnalysisRequest(
                evidence_id="synthetic-feedback-probe",
                image_width=256,
                image_height=256,
                task=vision.analysis_task,
            ),
            image=buffer.getvalue(),
        )
        assert assessment.image_assessment is not None and not assessment.detections
        report[phase] = {
            "status": "PASS",
            "provider": assessment.provider_name,
            "model_revision": assessment.model_revision,
            "threshold": assessment.image_assessment.threshold,
            "localized_detections": 0,
            "latency_ms": assessment.latency_ms,
        }
        phase = "embedding"
        assert settings.embedding_base_url is not None
        embedding = HTTPEmbeddingProvider(base_url=str(settings.embedding_base_url))
        vector = embedding.embed_query(
            "합성 문의 용기 파손 교환",
            DenseProfile(
                model_artifact="Qwen/Qwen3-Embedding-0.6B",
                model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
                embedding_dimension=1024,
                pooling_strategy="last_token",
                query_instruction="",
                max_query_tokens=8192,
                max_document_tokens=8192,
            ),
        )
        report[phase] = {
            "status": "PASS",
            "dimension": len(vector.values),
            "model_revision": vector.model_revision,
            "normalized": vector.normalized,
        }
        phase = "grounding"
        pack = CitationPack(
            id="synthetic-pack",
            tenant_id="synthetic",
            case_id="synthetic",
            retrieval_run_id="synthetic",
            retrieval_profile_hash="a" * 64,
            created_at=datetime.now(UTC),
            citations=(
                CitationSnapshot(
                    citation_id="CIT-001",
                    rank=1,
                    policy_clause_row_id="synthetic-row",
                    policy_clause_id="SYNTHETIC-1:C1",
                    document_id="SYNTHETIC-1",
                    document_version="1.0.0",
                    title="합성 테스트 정책",
                    section_path=("C1",),
                    clause_type=ClauseType.RULE,
                    text=(
                        "파손이 확인된 상품은 사진과 주문번호를 확인한 뒤 "
                        "담당자가 교환 가능 여부를 검토합니다."
                    ),
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    source_type="SYNTHETIC_REFERENCE",
                    source_hash="b" * 64,
                    query_strategy=QueryStrategy.RAW,
                    matched_query_ids=("Q1",),
                    retrieval_profile_hash="a" * 64,
                ),
            ),
        )
        if args.with_synthetic_rag:
            phase = "hybrid_rag"
            pack, report[phase] = synthetic_rag_pack(settings)
        phase = "grounding"
        grounding = build_llm_provider(settings, ModelReleaseTask.GROUNDED_POLICY_EXPLANATION_V1)
        explanation = grounding.explain_policy_grounded(
            GroundedExplanationInput(case_summary="합성 용기 파손 교환 문의", citation_pack=pack),
            _grounding_prompt(settings),
        )
        metrics = validate_grounded_explanation(explanation.explanation, pack)
        assert metrics.citation_id_valid_rate == 1.0 and metrics.statement_count > 0
        report[phase] = {
            "status": "PASS",
            "statements": metrics.statement_count,
            "citation_id_valid_rate": metrics.citation_id_valid_rate,
            "prompt_version": _grounding_prompt(settings).version,
            "latency_ms": explanation.metadata.latency_ms,
        }
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report[phase] = {"status": "FAIL", "error_type": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
