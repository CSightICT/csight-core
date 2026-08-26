"""Determinism, versioning, and fail-closed policy corpus validation tests."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.platform.policy_reference import (
    DocumentStatus,
    PolicyClause,
    PolicyDocument,
    build_corpus,
    parse_document,
    resolve_version,
    validate_corpus,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2] / "data/policy_corpus"


def _source() -> tuple[list[PolicyDocument], list[PolicyClause]]:
    documents = []
    clauses = []
    for path in sorted((ROOT / "raw").glob("*/*.md")):
        document, parsed = parse_document(path, root=ROOT)
        documents.append(document)
        clauses.extend(parsed)
    return documents, clauses


def test_corpus_meets_coverage_and_all_sources_are_synthetic() -> None:
    documents, clauses = _source()
    assert len(documents) == 24
    assert len(clauses) == 168
    assert {item.tenant_id for item in documents} == {
        "csight-demo-retail",
        "csight-demo-brand",
    }
    assert all(item.source_type == "SYNTHETIC_REFERENCE" for item in documents)
    assert sum(item.status is DocumentStatus.RETIRED for item in documents) == 6


def test_repeated_build_keeps_manifest_hash_and_stable_clause_ids() -> None:
    first = build_corpus(ROOT)
    first_ids = [
        json.loads(line)["clause_id"]
        for line in (ROOT / "clauses/policy_clauses_v1.jsonl").read_text().splitlines()
    ]
    second = build_corpus(ROOT)
    second_ids = [
        json.loads(line)["clause_id"]
        for line in (ROOT / "clauses/policy_clauses_v1.jsonl").read_text().splitlines()
    ]
    assert first["source_hash"] == second["source_hash"]
    assert first_ids == second_ids


def test_version_resolver_excludes_retired_and_future_versions() -> None:
    documents, _clauses = _source()
    resolved = resolve_version(
        tuple(documents),
        tenant_id="csight-demo-retail",
        document_id="POLICY-RTL-001",
        as_of=date(2026, 2, 1),
    )
    assert resolved is not None and resolved.document_version == "2.0.0"
    future = resolve_version(
        tuple(documents),
        tenant_id="csight-demo-retail",
        document_id="POLICY-RTL-009",
        as_of=date(2026, 2, 1),
    )
    assert future is None


def test_duplicate_clause_id_and_cross_tenant_parent_fail_validation() -> None:
    documents, clauses = _source()
    with pytest.raises(ValueError, match="duplicate clause_id"):
        validate_corpus(tuple(documents), tuple([*clauses, clauses[0]]))
    target = clauses[-1].model_copy(update={"parent_clause_id": clauses[0].clause_id})
    modified = [*clauses[:-1], target]
    with pytest.raises(ValueError, match="cross-tenant parent"):
        validate_corpus(tuple(documents), tuple(modified))


def test_cyclic_parent_and_mismatched_document_metadata_fail_validation() -> None:
    documents, clauses = _source()
    cyclic = [*clauses]
    cyclic[0] = cyclic[0].model_copy(update={"parent_clause_id": clauses[1].clause_id})
    cyclic[1] = cyclic[1].model_copy(update={"parent_clause_id": clauses[0].clause_id})
    with pytest.raises(ValueError, match="cyclic parent clause"):
        validate_corpus(tuple(documents), tuple(cyclic))

    mismatched = [*clauses]
    mismatched[0] = mismatched[0].model_copy(update={"policy_type": "WRONG_ITEM"})
    with pytest.raises(ValueError, match="metadata differs"):
        validate_corpus(tuple(documents), tuple(mismatched))


def test_supersession_must_be_reciprocal_and_active_document_must_not_be_expired() -> None:
    documents, clauses = _source()
    nonreciprocal = [*documents]
    nonreciprocal[0] = nonreciprocal[0].model_copy(update={"superseded_by": "POLICY-BRD-002@2.0.0"})
    with pytest.raises(ValueError, match="reciprocal"):
        validate_corpus(tuple(nonreciprocal), tuple(clauses))

    expired = [*documents]
    expired[1] = expired[1].model_copy(update={"effective_to": date(2025, 12, 31)})
    with pytest.raises(ValueError, match="effective_to is in the past"):
        validate_corpus(tuple(expired), tuple(clauses))


def test_quality_report_has_no_broken_reference_or_exact_duplicate() -> None:
    report = json.loads((ROOT / "reports/reference_data_quality_v1.json").read_text())
    assert report["broken_reference_count"] == 0
    assert report["cross_tenant_gold_violation_count"] == 0
    assert report["duplicate_count"] == 0
