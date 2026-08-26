"""Opt-in PostgreSQL verification for locked ACTIVE reranker execution profiles."""

import os

import pytest
from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyRerankerProfileModel,
    PolicyRetrievalExecutionProfileModel,
    TenantModel,
)
from app.adapters.persistence.reranker_profiles import SQLAlchemyPolicyExecutionProfileRepository
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration


def test_two_tenants_resolve_the_same_locked_reranker_contract() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test reranker profiles")
    settings = Settings()
    if not settings.database_url_value:
        pytest.fail("DATABASE_URL is required for reranker profile integration")
    factory = create_session_factory(get_engine(settings))
    repository = SQLAlchemyPolicyExecutionProfileRepository(factory)
    with factory() as session:
        tenants = tuple(
            session.scalars(
                select(TenantModel).where(
                    TenantModel.slug.in_(("csight-demo-brand", "csight-demo-retail"))
                )
            )
        )
        assert session.scalar(select(func.count(PolicyRerankerProfileModel.id))) == 1
        assert (
            session.scalar(
                select(func.count(PolicyRetrievalExecutionProfileModel.id)).where(
                    PolicyRetrievalExecutionProfileModel.status == "ACTIVE"
                )
            )
            == 2
        )
    profiles = tuple(
        repository.get_active_execution_profile(
            tenant_id=str(tenant.id), base_index_version="1.0.0"
        )
        for tenant in tenants
    )
    assert len(profiles) == 2
    assert {value.candidate_k for value in profiles} == {20}
    assert {value.final_k for value in profiles} == {10}
    assert {value.reranker.model_revision for value in profiles} == {
        "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    }
