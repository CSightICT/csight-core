"""Focused immutable-source and decision-hash regressions for Human Review."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.adapters.persistence import human_review as human_review_persistence
from app.adapters.persistence.grounding import load_verified_citation_pack
from app.adapters.persistence.models import (
    HumanReviewDecisionBasisModel,
    HumanReviewDecisionModel,
    PolicyCitationPackItemModel,
    PolicyCitationPackModel,
)
from app.platform.errors import ValidationError
from app.platform.grounding import CitationPack, CitationSnapshot
from app.platform.human_review import canonical_hash
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import QueryStrategy

pytestmark = pytest.mark.unit


def test_citation_pack_verifier_recomputes_hash_from_rows() -> None:
    now = datetime.now(UTC)
    tenant_id, case_id, run_id, pack_id, clause_id = (uuid4() for _ in range(5))
    profile_hash = "a" * 64
    snapshot = CitationSnapshot(
        citation_id="CIT-001",
        rank=1,
        policy_clause_row_id=str(clause_id),
        policy_clause_id="refund.general.1",
        document_id="refund-policy",
        document_version="1.0.0",
        title="Refund policy",
        section_path=("Refund",),
        clause_type=ClauseType.RULE,
        text="Refunds require a valid order reference.",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_type="SYNTHETIC",
        source_hash="b" * 64,
        query_strategy=QueryStrategy.RAW,
        matched_query_ids=("Q1",),
        retrieval_profile_hash=profile_hash,
    )
    expected = CitationPack(
        id=str(pack_id),
        tenant_id=str(tenant_id),
        case_id=str(case_id),
        retrieval_run_id=str(run_id),
        retrieval_profile_hash=profile_hash,
        citations=(snapshot,),
        created_at=now,
    )
    pack_row = PolicyCitationPackModel(
        id=pack_id,
        tenant_id=tenant_id,
        case_id=case_id,
        retrieval_run_id=run_id,
        schema_version="1.0",
        retrieval_profile_hash=profile_hash,
        content_hash=expected.content_hash,
        created_at=now,
    )
    item_row = PolicyCitationPackItemModel(
        id=uuid4(),
        tenant_id=tenant_id,
        citation_pack_id=pack_id,
        citation_id="CIT-001",
        rank=1,
        policy_clause_row_id=clause_id,
        policy_clause_id=snapshot.policy_clause_id,
        document_id=snapshot.document_id,
        document_version=snapshot.document_version,
        title=snapshot.title,
        section_path=list(snapshot.section_path),
        clause_type=snapshot.clause_type.value,
        clause_text=snapshot.text,
        effective_from=snapshot.effective_from,
        effective_to=snapshot.effective_to,
        source_type=snapshot.source_type,
        source_hash=snapshot.source_hash,
        retrieval_mode="HYBRID",
        query_strategy=snapshot.query_strategy.value,
        matched_query_ids=list(snapshot.matched_query_ids),
        retrieval_profile_hash=profile_hash,
        created_at=now,
    )
    session = MagicMock()
    session.scalar.return_value = pack_row
    session.scalars.return_value.all.return_value = [item_row]

    assert (
        load_verified_citation_pack(session, tenant_id, pack_id).content_hash
        == expected.content_hash
    )

    item_row.clause_text = "tampered citation text"
    with pytest.raises(ValidationError, match="content hash"):
        load_verified_citation_pack(session, tenant_id, pack_id)


def test_decision_hash_covers_audit_identity_time_and_typed_targets() -> None:
    now = datetime.now(UTC)
    decision = HumanReviewDecisionModel(
        id=uuid4(),
        tenant_id=uuid4(),
        review_task_id=uuid4(),
        decision_type="APPROVE_REFUND",
        reason_codes=["POLICY_MATCH"],
        rationale="The policy rule and evidence support this outcome.",
        outcome_relation="CONSISTENT_WITH_RECOMMENDATION",
        outcome_relation_rule_version="1.0.0",
        decided_by=uuid4(),
        decided_at=now,
        decision_schema_version="1.0.0",
        content_hash="0" * 64,
        created_at=now,
    )
    basis = HumanReviewDecisionBasisModel(
        id=uuid4(),
        tenant_id=decision.tenant_id,
        human_review_decision_id=decision.id,
        basis_type="POLICY_RULE_RESULT",
        reference_id=str(uuid4()),
        policy_rule_result_id=uuid4(),
        policy_clause_row_id=None,
        citation_item_id=None,
        case_evidence_id=None,
        analysis_result_id=None,
        created_at=now,
    )
    payload = human_review_persistence._decision_hash_payload  # pyright: ignore[reportPrivateUsage]
    baseline = canonical_hash(payload(decision, reason_codes=["POLICY_MATCH"], basis_rows=[basis]))

    original_target = basis.policy_rule_result_id
    basis.policy_rule_result_id = uuid4()
    assert (
        canonical_hash(payload(decision, reason_codes=["POLICY_MATCH"], basis_rows=[basis]))
        != baseline
    )
    basis.policy_rule_result_id = original_target

    decision.decided_at = now + timedelta(microseconds=1)
    assert (
        canonical_hash(payload(decision, reason_codes=["POLICY_MATCH"], basis_rows=[basis]))
        != baseline
    )
