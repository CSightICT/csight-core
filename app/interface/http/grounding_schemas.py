"""HTTP schemas for citation packs and grounded explanation runs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.platform.grounding import GroundedExplanationRun
from app.ports.grounding import GroundedExplanationRunDetail


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartGroundedExplanationRequest(_Schema):
    retrieval_run_id: str = Field(min_length=1)


class GroundedExplanationRunResponse(_Schema):
    id: str
    case_id: str
    retrieval_run_id: str
    citation_pack_id: str
    status: str
    correlation_id: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_run(cls, run: GroundedExplanationRun) -> "GroundedExplanationRunResponse":
        # Project an explicit public allowlist as the internal run model evolves.
        return cls(**run.model_dump(include=set(cls.model_fields)))


class GroundedExplanationRunListResponse(_Schema):
    items: tuple[GroundedExplanationRunResponse, ...]


class GroundedExplanationRunDetailResponse(_Schema):
    run: GroundedExplanationRunResponse
    citation_pack: dict[str, object]
    explanation: dict[str, object] | None
    structural_validation: dict[str, object] | None
    semantic_evaluation_status: str = "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE"

    @classmethod
    def from_detail(
        cls, detail: GroundedExplanationRunDetail
    ) -> "GroundedExplanationRunDetailResponse":
        pack = detail.citation_pack.model_dump(
            mode="json",
            exclude={"tenant_id"},
        )
        citations = pack.get("citations")
        if isinstance(citations, list):
            for citation in citations:
                if isinstance(citation, dict):
                    citation.pop("policy_clause_row_id", None)
        return cls(
            run=GroundedExplanationRunResponse.from_run(detail.run),
            citation_pack=pack,
            explanation=(
                detail.explanation.model_dump(mode="json") if detail.explanation else None
            ),
            structural_validation=(
                detail.validation_metrics.model_dump(mode="json")
                if detail.validation_metrics
                else None
            ),
        )


__all__ = [
    "GroundedExplanationRunDetailResponse",
    "GroundedExplanationRunListResponse",
    "GroundedExplanationRunResponse",
    "StartGroundedExplanationRequest",
]
