"""Deterministic and fail-closed tests for the local csight policy bundle."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.adapters.persistence.models import PolicyClauseModel, PolicyDocumentModel
from app.platform.analysis.enums import MissingInformation
from app.platform.policy_engine import PolicyEffectType, PolicyRuleSet, canonical_hash
from app.platform.policy_reference import (
    ClauseType,
    DocumentStatus,
    PolicyClause,
    PolicyDocument,
    sha256_text,
)
from app.platform.policy_retrieval import (
    PolicyClauseRecord,
    PolicyIndexStatus,
    serialize_policy_clause,
)
from scripts.build_policy_embeddings import (
    PROFILE_ID,
    CorpusIndexMetadata,
    PersistedEmbeddingSnapshot,
    PersistedIndexSnapshot,
    load_single_tenant_manifest,
    validate_persisted_embedding_integrity,
    validate_protected_index_state,
)
from scripts.prepare_csight_synthetic_policy_runtime import (
    CORPUS_NAME,
    CORPUS_VERSION,
    EXPECTED_CLAUSE_COUNT,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_LEGACY_CLAUSE_COUNT,
    EXPECTED_LEGACY_DOCUMENT_COUNT,
    EXPECTED_RULE_COUNT,
    EXPECTED_V2_CLAUSE_COUNT,
    EXPECTED_V2_DOCUMENT_COUNT,
    EXPECTED_V2_RULE_COUNT,
    FAULTY_RULE_SET_HISTORY_PATH,
    FAULTY_RULE_SET_VERSION,
    LEGACY_CORPUS_VERSION,
    LEGACY_RULE_SET_VERSION,
    POLICY_DOCUMENT_VERSION,
    RULE_SET_VERSION,
    SOURCE_TENANT,
    TARGET_TENANT,
    PolicyRuntimePreparationError,
    materialize_policy_bundle,
    require_local_or_test,
    require_local_runtime,
    validate_persisted_policy_semantics,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
SOURCE_CORPUS = ROOT / "data" / "policy_corpus"
SOURCE_RULES = ROOT / "data" / "policy_rules" / "normalized" / "policy_rule_sets_v1.jsonl"


def _materialize(output: Path):
    return materialize_policy_bundle(
        source_corpus_root=SOURCE_CORPUS,
        source_rules_path=SOURCE_RULES,
        output_root=output,
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_bundle_recomputes_raw_clause_corpus_and_rule_source_hashes(tmp_path: Path) -> None:
    bundle = _materialize(tmp_path / "bundle")
    documents = tuple(
        PolicyDocument.model_validate_json(line)
        for line in (bundle.corpus_root / "normalized" / "policy_documents_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    clauses = tuple(
        PolicyClause.model_validate_json(line)
        for line in (bundle.corpus_root / "clauses" / "policy_clauses_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    manifest = json.loads(bundle.corpus_manifest.read_text(encoding="utf-8"))
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in bundle.rules_path.read_text(encoding="utf-8").splitlines()
        if line
    )
    rule_set = next(item for item in rule_sets if item.rule_set_version == RULE_SET_VERSION)
    legacy_rule_set = next(
        item for item in rule_sets if item.rule_set_version == LEGACY_RULE_SET_VERSION
    )
    rules_manifest = json.loads(bundle.rules_manifest.read_text(encoding="utf-8"))
    faulty_history = PolicyRuleSet.model_validate_json(
        (bundle.root / FAULTY_RULE_SET_HISTORY_PATH).read_text(encoding="utf-8")
    )

    assert len(documents) == EXPECTED_DOCUMENT_COUNT
    assert len(clauses) == EXPECTED_CLAUSE_COUNT
    assert sum(len(item.rules) for item in rule_sets) == EXPECTED_RULE_COUNT
    assert {item.rule_set_version for item in rule_sets} == {
        LEGACY_RULE_SET_VERSION,
        RULE_SET_VERSION,
    }
    assert faulty_history.rule_set_version == FAULTY_RULE_SET_VERSION
    assert rules_manifest["known_faulty_history_content_hash"] == faulty_history.content_hash
    assert faulty_history not in rule_sets
    assert len(rule_set.rules) == EXPECTED_V2_RULE_COUNT
    assert {item.tenant_id for item in documents} == {TARGET_TENANT}
    assert {item.tenant_id for item in clauses} == {TARGET_TENANT}
    assert {item.tenant_slug for item in rule_sets} == {TARGET_TENANT}
    assert all(item.source_type == "SYNTHETIC_REFERENCE" for item in documents)
    assert all(item.source_type == "SYNTHETIC_REFERENCE" for item in clauses)
    assert SOURCE_TENANT not in "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((bundle.corpus_root / "raw" / TARGET_TENANT).glob("*.md"))
    )

    raw_by_path = {
        str(path.relative_to(bundle.corpus_root)): path
        for path in (bundle.corpus_root / "raw" / TARGET_TENANT).glob("*.md")
    }
    for document in documents:
        raw_text = raw_by_path[document.source_path].read_text(encoding="utf-8")
        assert document.source_hash == sha256_text(unicodedata.normalize("NFC", raw_text))
    document_hashes = {
        (item.document_id, item.document_version): item.source_hash for item in documents
    }
    assert manifest["source_hash"] == sha256_text(
        "".join(document.source_hash for document in documents)
    )
    assert manifest["document_count"] == len(documents)
    assert manifest["clause_count"] == len(clauses)
    assert manifest["tenant_count"] == 1
    assert manifest["source_type"] == "SYNTHETIC_REFERENCE"
    for clause in clauses:
        assert clause.content_hash == sha256_text(clause.text)
        assert clause.source_hash == document_hashes[(clause.document_id, clause.document_version)]
    clause_map = {item.clause_id: item for item in clauses}
    for item in rule_sets:
        for rule in item.rules:
            for source in rule.source_references:
                clause = clause_map[source.clause_id]
                assert source.document_id == clause.document_id
                assert source.document_version == clause.document_version
                assert source.source_hash == clause.source_hash
                assert clause.document_status.value == "ACTIVE"
    assert rule_set.source_corpus_hash == manifest["source_hash"]
    legacy_documents = tuple(
        item for item in documents if not item.document_id.startswith("CSC-OPS-")
    )
    assert legacy_rule_set.source_corpus_version == LEGACY_CORPUS_VERSION
    assert legacy_rule_set.source_corpus_hash == sha256_text(
        "".join(item.source_hash for item in legacy_documents)
    )
    assert rules_manifest["active_rule_set_version"] == RULE_SET_VERSION
    assert rules_manifest["content_hash"] == canonical_hash(
        [item.model_dump(mode="json") for item in rule_sets]
    )
    assert tuple((item.rule_id, item.rule_version) for item in rule_set.rules) == tuple(
        sorted((item.rule_id, item.rule_version) for item in rule_set.rules)
    )
    assert all(
        tuple(
            (
                source.clause_id,
                source.document_id,
                source.document_version,
                source.source_hash,
            )
            for source in rule.source_references
        )
        == tuple(
            sorted(
                (
                    source.clause_id,
                    source.document_id,
                    source.document_version,
                    source.source_hash,
                )
                for source in rule.source_references
            )
        )
        for rule in rule_set.rules
    )


def test_v2_is_fictional_complete_and_preserves_human_only_decisions(tmp_path: Path) -> None:
    bundle = _materialize(tmp_path / "bundle")
    documents = tuple(
        PolicyDocument.model_validate_json(line)
        for line in (bundle.corpus_root / "normalized" / "policy_documents_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    clauses = tuple(
        PolicyClause.model_validate_json(line)
        for line in (bundle.corpus_root / "clauses" / "policy_clauses_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    v2_rule_set = next(
        PolicyRuleSet.model_validate_json(line)
        for line in bundle.rules_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["rule_set_version"] == RULE_SET_VERSION
    )
    v2_documents = tuple(item for item in documents if item.document_id.startswith("CSC-OPS-"))
    v2_clauses = tuple(item for item in clauses if item.document_id.startswith("CSC-OPS-"))
    raw_v2 = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((bundle.corpus_root / "raw" / TARGET_TENANT).glob("csc-ops-*.md"))
    )

    assert len(v2_documents) == EXPECTED_V2_DOCUMENT_COUNT
    assert len(v2_clauses) == EXPECTED_V2_CLAUSE_COUNT
    assert len(documents) - len(v2_documents) == EXPECTED_LEGACY_DOCUMENT_COUNT
    assert len(clauses) - len(v2_clauses) == EXPECTED_LEGACY_CLAUSE_COUNT
    assert {item.document_version for item in v2_documents} == {POLICY_DOCUMENT_VERSION}
    assert all(item.status is DocumentStatus.ACTIVE for item in v2_documents)
    assert "완전 가상" in raw_v2
    assert "실제 기업 정책이나 법률 자문" in raw_v2
    assert "쿠팡" not in raw_v2
    assert "아마존" not in raw_v2
    for required_term in (
        "반품",
        "교환",
        "환불",
        "재배송",
        "수리",
        "정보 안내",
        "배송손상",
        "초기불량",
        "누액",
        "100000원",
        "14일",
        "관리자",
        "무하자 단순변심",
        "반품비 부담",
        "환불 안내 시점",
    ):
        assert required_term in raw_v2

    allowed_effects = set(PolicyEffectType)
    assert all(rule.prohibit_final_decision for rule in v2_rule_set.rules)
    assert all(rule.requires_human_review for rule in v2_rule_set.rules)
    assert all(
        any(
            effect.type
            in {PolicyEffectType.REQUIRE_HUMAN_REVIEW, PolicyEffectType.REQUIRE_MANAGER_REVIEW}
            for effect in rule.effects
        )
        for rule in v2_rule_set.rules
    )
    assert {effect.type for rule in v2_rule_set.rules for effect in rule.effects} <= allowed_effects
    assert all(
        source.document_id.startswith("CSC-OPS-")
        and source.document_version == POLICY_DOCUMENT_VERSION
        for rule in v2_rule_set.rules
        for source in rule.source_references
    )
    eligibility_values = {
        effect.value
        for rule in v2_rule_set.rules
        for effect in rule.effects
        if effect.type is PolicyEffectType.MARK_REVIEW_ELIGIBILITY
    }
    assert {
        "RETURN_REVIEW",
        "EXCHANGE_REVIEW",
        "REFUND_REVIEW",
        "REPAIR_REVIEW",
        "INFORMATION_REVIEW",
        "RESHIPMENT_REVIEW",
    } <= eligibility_values


def test_v2_rule_sources_trace_normal_change_of_mind_and_refund_timing(tmp_path: Path) -> None:
    bundle = _materialize(tmp_path / "bundle")
    v2_rule_set = next(
        PolicyRuleSet.model_validate_json(line)
        for line in bundle.rules_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["rule_set_version"] == RULE_SET_VERSION
    )
    rules = {item.rule_id: item for item in v2_rule_set.rules}

    assert {item.clause_id for item in rules["CSC-POLICY-201"].source_references} >= {
        "CSC-OPS-RET-001:2.0.0:C7",
        "CSC-OPS-FIN-006:2.0.0:C7",
    }
    assert {item.clause_id for item in rules["CSC-POLICY-203"].source_references} >= {
        "CSC-OPS-RET-001:2.0.0:C8",
        "CSC-OPS-FIN-006:2.0.0:C8",
    }
    assert {item.clause_id for item in rules["CSC-POLICY-205"].source_references} >= {
        "CSC-OPS-RET-001:2.0.0:C8",
        "CSC-OPS-FIN-006:2.0.0:C8",
    }
    missing_information_rule = rules["CSC-POLICY-214"]
    assert missing_information_rule.conditions[0].expected == [
        "IMAGE_EVIDENCE",
        "CUSTOMER_REQUEST",
    ]
    assert set(missing_information_rule.conditions[0].expected) <= {
        item.value for item in MissingInformation
    }


def test_repeated_materialization_reuses_only_byte_identical_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    first = _materialize(output)
    first_tree = _tree(output)
    second = _materialize(output)

    assert first.reused is False
    assert second.reused is True
    assert _tree(output) == first_tree

    readme = output / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    changed = readme.read_bytes()
    with pytest.raises(PolicyRuntimePreparationError) as captured:
        _materialize(output)
    assert captured.value.code == "OUTPUT_CONTENT_MISMATCH"
    assert readme.read_bytes() == changed


def test_manifest_loader_and_environment_guard_fail_closed(tmp_path: Path) -> None:
    bundle = _materialize(tmp_path / "bundle")
    metadata = load_single_tenant_manifest(bundle.corpus_manifest)
    assert metadata.source_hash == bundle.corpus_source_hash
    assert metadata.document_count == EXPECTED_DOCUMENT_COUNT
    assert metadata.clause_count == EXPECTED_CLAUSE_COUNT

    require_local_or_test("local")
    require_local_or_test("TEST")
    with pytest.raises(PolicyRuntimePreparationError) as captured:
        require_local_or_test("production")
    assert captured.value.code == "ENVIRONMENT_NOT_ALLOWED"

    invalid_manifest = tmp_path / "invalid.json"
    payload = json.loads(bundle.corpus_manifest.read_text(encoding="utf-8"))
    payload["source_type"] = "ENTERPRISE_POLICY"
    invalid_manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SYNTHETIC_REFERENCE"):
        load_single_tenant_manifest(invalid_manifest)


def test_runtime_guard_accepts_only_loopback_database_and_http_embedding() -> None:
    embedding_url = require_local_runtime(
        environment="local",
        database_url="postgresql+psycopg://user:secret@localhost:5432/csight",
        embedding_base_url="http://[::1]:8091/",
    )

    assert embedding_url == "http://[::1]:8091"


@pytest.mark.parametrize(
    ("environment", "database_url", "embedding_url"),
    (
        (
            "production",
            "postgresql+psycopg://user:secret@localhost:5432/csight",
            "http://127.0.0.1:8091",
        ),
        (
            "local",
            "postgresql+psycopg://user:secret@db.internal:5432/csight",
            "http://127.0.0.1:8091",
        ),
        ("test", "sqlite:///local.db", "http://127.0.0.1:8091"),
        (
            "test",
            "postgresql+psycopg://user:secret@127.0.0.1:5432/csight",
            "https://127.0.0.1:8091",
        ),
        (
            "test",
            "postgresql+psycopg://user:secret@127.0.0.1:5432/csight",
            "http://localhost.evil:8091",
        ),
        (
            "test",
            "postgresql+psycopg://user:secret@127.0.0.1:5432/csight",
            "http://127.0.0.1:8091/v1",
        ),
    ),
)
def test_runtime_guard_rejects_nonlocal_targets(
    environment: str, database_url: str, embedding_url: str
) -> None:
    with pytest.raises(PolicyRuntimePreparationError):
        require_local_runtime(
            environment=environment,
            database_url=database_url,
            embedding_base_url=embedding_url,
        )


def test_protected_embedding_replay_validates_passage_hash_dimension_and_values() -> None:
    clause = PolicyClauseRecord(
        row_id=str(uuid4()),
        tenant_id=str(uuid4()),
        document_id="returns",
        document_version="1.0",
        title="Synthetic Returns",
        clause_id="returns:1.0:eligibility",
        section_path=("Eligibility",),
        clause_type=ClauseType.RULE,
        text="Synthetic demo text only.",
        parent_clause_id=None,
        policy_type="RETURN_REFUND",
        product_categories=("GENERAL",),
        defect_types=("CRACK",),
        actions=("REVIEW",),
        requires_human_review=True,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC).date(),
        effective_to=None,
        document_status=DocumentStatus.ACTIVE,
        source_type="SYNTHETIC_REFERENCE",
        source_hash="b" * 64,
    )
    expected_hash = hashlib.sha256(serialize_policy_clause(clause).encode()).hexdigest()
    valid = PersistedEmbeddingSnapshot(
        policy_clause_row_id=UUID(clause.row_id),
        document_text_hash=expected_hash,
        embedding_dimension=1024,
        embedding=(0.0,) * 1024,
    )

    validate_persisted_embedding_integrity((clause,), (valid,), require_complete=True)
    with pytest.raises(ValueError, match="text hash"):
        validate_persisted_embedding_integrity(
            (clause,), (replace(valid, document_text_hash="c" * 64),), require_complete=True
        )
    with pytest.raises(ValueError, match="dimension"):
        validate_persisted_embedding_integrity(
            (clause,), (replace(valid, embedding_dimension=512),), require_complete=True
        )
    with pytest.raises(ValueError, match="NaN"):
        validate_persisted_embedding_integrity(
            (clause,),
            (replace(valid, embedding=(float("nan"),) + (0.0,) * 1023),),
            require_complete=True,
        )
    with pytest.raises(ValueError, match="incomplete"):
        validate_persisted_embedding_integrity((clause,), (), require_complete=True)


def test_protected_index_must_already_be_clean_active() -> None:
    metadata = CorpusIndexMetadata(
        name=CORPUS_NAME,
        version=CORPUS_VERSION,
        source_hash="a" * 64,
        document_count=1,
        clause_count=1,
    )
    active = PersistedIndexSnapshot(
        index_name="csight_policy_reference",
        index_version="1.0.0",
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        corpus_source_hash="a" * 64,
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
        status=PolicyIndexStatus.ACTIVE.value,
        expected_clause_count=1,
        indexed_clause_count=1,
        activated_at=datetime(2026, 8, 28, tzinfo=UTC),
        retired_at=None,
    )
    validate_protected_index_state(active, metadata=metadata, expected_clause_count=1)

    for invalid in (
        replace(active, status=PolicyIndexStatus.BUILDING.value),
        replace(active, status=PolicyIndexStatus.RETIRED.value),
        replace(active, indexed_clause_count=0),
        replace(active, activated_at=None),
        replace(active, retired_at=datetime(2026, 8, 28, tzinfo=UTC)),
    ):
        with pytest.raises(ValueError, match="clean ACTIVE"):
            validate_protected_index_state(invalid, metadata=metadata, expected_clause_count=1)


def test_persisted_policy_semantics_rejects_content_or_metadata_drift(tmp_path: Path) -> None:
    bundle = _materialize(tmp_path / "bundle")
    documents = tuple(
        PolicyDocument.model_validate_json(line)
        for line in (bundle.corpus_root / "normalized" / "policy_documents_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    clauses = tuple(
        PolicyClause.model_validate_json(line)
        for line in (bundle.corpus_root / "clauses" / "policy_clauses_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    document = documents[0]
    clause = next(
        item
        for item in clauses
        if (item.document_id, item.document_version)
        == (document.document_id, document.document_version)
    )
    tenant_id = uuid4()
    document_row_id = uuid4()
    supersedes = document.supersedes.split("@", 1) if document.supersedes else (None, None)
    superseded_by = document.superseded_by.split("@", 1) if document.superseded_by else (None, None)
    document_row = PolicyDocumentModel(
        id=document_row_id,
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
        ingestion_run_id=uuid4(),
    )
    clause_row = PolicyClauseModel(
        id=uuid4(),
        tenant_id=tenant_id,
        document_row_id=document_row_id,
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
        ingestion_run_id=uuid4(),
    )
    validate_persisted_policy_semantics(
        documents=documents,
        clauses=clauses,
        persisted_documents=(document_row,),
        persisted_clauses=(clause_row,),
        require_complete=False,
    )

    document_row.authority_level = "TAMPERED"
    with pytest.raises(PolicyRuntimePreparationError, match="document semantics"):
        validate_persisted_policy_semantics(
            documents=documents,
            clauses=clauses,
            persisted_documents=(document_row,),
            persisted_clauses=(clause_row,),
            require_complete=False,
        )
    document_row.authority_level = document.authority_level
    clause_row.text = "tampered without updating the stored hashes"
    with pytest.raises(PolicyRuntimePreparationError, match="clause semantics"):
        validate_persisted_policy_semantics(
            documents=documents,
            clauses=clauses,
            persisted_documents=(document_row,),
            persisted_clauses=(clause_row,),
            require_complete=False,
        )


def test_materialization_rejects_stale_source_rule_corpus_hash(tmp_path: Path) -> None:
    rule_rows = [
        json.loads(line) for line in SOURCE_RULES.read_text(encoding="utf-8").splitlines() if line
    ]
    brand_rule = next(row for row in rule_rows if row["tenant_slug"] == SOURCE_TENANT)
    brand_rule["source_corpus_hash"] = "f" * 64
    stale_rules = tmp_path / "stale-rules.jsonl"
    stale_rules.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rule_rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicyRuntimePreparationError) as captured:
        materialize_policy_bundle(
            source_corpus_root=SOURCE_CORPUS,
            source_rules_path=stale_rules,
            output_root=tmp_path / "bundle",
        )
    assert captured.value.code == "SOURCE_RULE_CORPUS_HASH_MISMATCH"
