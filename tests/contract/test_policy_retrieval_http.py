"""HTTP contract tests for the authenticated read-only retrieval route."""

from datetime import date
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer, Sprint4BServiceContainer
from app.main import create_app
from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import (
    DenseProfile,
    EmbeddingProviderUnavailableError,
    HybridFusionProfile,
    LexicalProfile,
    PolicyClauseRecord,
    PolicyRetrievalProfile,
    PolicyRetrievalResult,
    PolicySearchHit,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.contract


class Resolver:
    def execute(self, token: str) -> Principal:
        assert token == "valid"
        return Principal(
            user_id="user-a",
            tenant_id="tenant-a",
            email="reviewer@example.test",
            display_name="Reviewer",
            roles=frozenset({Role.REVIEWER}),
        )


class Search:
    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.tenant_id: str | None = None

    def execute(self, *, principal: Principal, query: object) -> PolicyRetrievalResult:
        if self.down:
            raise EmbeddingProviderUnavailableError()
        typed_query = cast(Any, query)
        self.tenant_id = typed_query.tenant_id
        clause = PolicyClauseRecord(
            row_id="row-1",
            tenant_id=principal.tenant_id,
            document_id="POLICY-A",
            document_version="1.0.0",
            title="정책",
            clause_id="POLICY-A:1.0.0:C1",
            section_path=("정책", "C1"),
            clause_type=ClauseType.RULE,
            text="참조 조항",
            policy_type="RETURN_EXCHANGE",
            product_categories=("GENERAL",),
            defect_types=("LEAKAGE",),
            actions=("REVIEW",),
            requires_human_review=False,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            document_status=DocumentStatus.ACTIVE,
            source_type="SYNTHETIC_REFERENCE",
            source_hash="a" * 64,
        )
        profile = PolicyRetrievalProfile(
            lexical=LexicalProfile(),
            dense=DenseProfile(
                model_artifact="Qwen/Qwen3-Embedding-0.6B",
                model_revision="r",
                embedding_dimension=1024,
                pooling_strategy="last-token",
                query_instruction="instruction",
                max_query_tokens=8192,
                max_document_tokens=8192,
            ),
            fusion=HybridFusionProfile(),
            embedding_profile_id="profile-id",
            index_version="1.0.0",
        )
        return PolicyRetrievalResult(
            query_hash=typed_query.query_hash,
            mode=typed_query.mode,
            as_of_date=typed_query.as_of_date,
            retrieval_profile=profile,
            hits=(PolicySearchHit(clause=clause, lexical_rank=1, lexical_score=1.0),),
            latency_ms=1.0,
        )


def client(search: Search) -> TestClient:
    resolver = Resolver()
    sprint1 = Sprint1ServiceContainer(
        authenticate_user=cast(Any, resolver),
        resolve_principal=resolver,
        create_case=cast(Any, resolver),
        list_cases=cast(Any, resolver),
        get_case=cast(Any, resolver),
        get_case_status_history=cast(Any, resolver),
        add_image_evidence=cast(Any, resolver),
        list_case_evidence=cast(Any, resolver),
        get_evidence_metadata=cast(Any, resolver),
        create_evidence_access_url=cast(Any, resolver),
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            sprint4b_services=Sprint4BServiceContainer(search_policy_clauses=cast(Any, search)),
        )
    )


def request_body(mode: str = "LEXICAL") -> dict[str, object]:
    return {
        "query": "누액 상품 교환 조건",
        "as_of_date": "2026-02-01",
        "mode": mode,
        "top_k": 5,
        "filters": {"defect_types": ["LEAKAGE"]},
    }


def test_api_uses_principal_tenant_and_returns_clause_only() -> None:
    search = Search()
    response = client(search).post(
        "/api/v1/policy-retrieval/search",
        headers={"Authorization": "Bearer valid"},
        json=request_body(),
    )
    assert response.status_code == 200
    assert search.tenant_id == "tenant-a"
    assert response.json()["hits"][0]["clause_id"] == "POLICY-A:1.0.0:C1"
    assert "decision" not in response.text
    assert "embedding_profile_id" not in response.text


@pytest.mark.parametrize(
    "body",
    (
        {**request_body(), "query": ""},
        {**request_body(), "top_k": 0},
        {**request_body(), "top_k": 21},
        {**request_body(), "mode": "UNKNOWN"},
        {**request_body(), "filters": {"defect_types": ["UNKNOWN"]}},
        {**request_body(), "tenant_id": "tenant-b"},
    ),
)
def test_api_rejects_invalid_or_tenant_supplied_input(body: dict[str, object]) -> None:
    response = client(Search()).post(
        "/api/v1/policy-retrieval/search",
        headers={"Authorization": "Bearer valid"},
        json=body,
    )
    assert response.status_code == 422


def test_embedding_provider_down_is_safe_503() -> None:
    response = client(Search(down=True)).post(
        "/api/v1/policy-retrieval/search",
        headers={"Authorization": "Bearer valid"},
        json=request_body("DENSE"),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMBEDDING_PROVIDER_UNAVAILABLE"
    assert "traceback" not in response.text.lower()
