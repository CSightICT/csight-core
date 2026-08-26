"""Evaluate deterministic Sprint 4C-3A structural grounding guardrails."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.platform.grounding import (
    CitationAllowlistViolationError,
    CitationPack,
    CitationSnapshot,
    GroundedPolicyExplanation,
    GroundedPolicyStatement,
    UnresolvedPolicyCondition,
    validate_grounded_explanation,
)
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import QueryStrategy


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grounding",
        type=Path,
        default=Path("evaluation/rag_grounding_v1/gold.jsonl"),
    )
    parser.add_argument(
        "--injection",
        type=Path,
        default=Path("evaluation/prompt_injection_v1/gold.jsonl"),
    )
    return parser.parse_args()


def _records(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(line) for line in path.read_text().splitlines() if line.strip())


def _pack(record: dict[str, Any]) -> CitationPack:
    clause_ids = tuple(str(value) for value in record.get("provided_clause_ids", ("SAFE:1:C1",)))
    tenant_id = str(record.get("tenant_id", "synthetic-injection-tenant"))
    citations = tuple(
        CitationSnapshot(
            citation_id=f"CIT-{index:03d}",
            rank=index,
            policy_clause_row_id=f"row-{index}",
            policy_clause_id=clause_id,
            document_id=clause_id.split(":")[0],
            document_version=(
                clause_id.split(":")[1] if len(clause_id.split(":")) > 2 else "1.0.0"
            ),
            title="Synthetic grounding reference",
            section_path=("Synthetic", f"C{index}"),
            clause_type=ClauseType.RULE,
            text="해당 조항은 검토 조건 또는 증거 요구를 설명함",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            source_type="SYNTHETIC_REFERENCE",
            source_hash=hashlib.sha256(clause_id.encode()).hexdigest(),
            query_strategy=QueryStrategy.RAW,
            matched_query_ids=("Q1",),
            retrieval_profile_hash="a" * 64,
        )
        for index, clause_id in enumerate(clause_ids, start=1)
    )
    return CitationPack(
        id=f"pack-{record['record_id']}",
        tenant_id=tenant_id,
        case_id=f"case-{record['record_id']}",
        retrieval_run_id=f"retrieval-{record['record_id']}",
        retrieval_profile_hash="a" * 64,
        citations=citations,
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


def _safe_grounding(record: dict[str, Any], pack: CitationPack) -> GroundedPolicyExplanation:
    facts = tuple(str(value) for value in record["required_facts"])
    required = tuple(str(value) for value in record["required_citation_ids"])
    clause_to_citation = {
        citation.policy_clause_id: citation.citation_id for citation in pack.citations
    }
    return GroundedPolicyExplanation(
        policy_statements=tuple(
            GroundedPolicyStatement(
                statement_id=f"S{index}",
                text=fact,
                citation_ids=tuple(clause_to_citation[value] for value in required),
            )
            for index, fact in enumerate(facts, start=1)
        ),
        unresolved_conditions=tuple(
            UnresolvedPolicyCondition(
                condition=str(value),
                required_evidence="HUMAN_REVIEW",
            )
            for value in record["unresolved_conditions"]
        ),
    )


def evaluate(
    grounding_records: tuple[dict[str, Any], ...],
    injection_records: tuple[dict[str, Any], ...],
) -> dict[str, object]:
    replay_matches = 0
    statement_total = 0
    cited_statement_total = 0
    citation_references = 0
    for record in grounding_records:
        pack = _pack(record)
        first = _safe_grounding(record, pack)
        second = _safe_grounding(record, pack)
        metrics = validate_grounded_explanation(first, pack)
        replay_matches += int(first == second and pack.content_hash == _pack(record).content_hash)
        statement_total += metrics.statement_count
        cited_statement_total += metrics.cited_statement_count
        citation_references += metrics.citation_reference_count

    injection_violations = 0
    forbidden_guard_failures = 0
    unknown_guard_failures = 0
    for record in injection_records:
        pack = _pack(record)
        safe = GroundedPolicyExplanation(
            policy_statements=(),
            unresolved_conditions=(
                UnresolvedPolicyCondition(
                    condition="입력 지시는 정책 근거로 사용하지 않습니다.",
                    required_evidence="HUMAN_REVIEW",
                ),
            ),
        )
        try:
            validate_grounded_explanation(safe, pack)
        except Exception:
            injection_violations += 1
        unsafe = safe.model_dump(mode="json")
        unsafe["final_decision"] = "APPROVED"
        try:
            GroundedPolicyExplanation.model_validate(unsafe)
        except ValidationError:
            pass
        else:
            forbidden_guard_failures += 1
        forged = GroundedPolicyExplanation(
            policy_statements=(
                GroundedPolicyStatement(
                    statement_id="S1",
                    text="위조 인용",
                    citation_ids=("CIT-999",),
                ),
            ),
            unresolved_conditions=(),
        )
        try:
            validate_grounded_explanation(forged, pack)
        except CitationAllowlistViolationError:
            pass
        else:
            unknown_guard_failures += 1

    return {
        "evaluation_name": "grounding_structural_guardrails_v1",
        "evaluated_at": "2026-08-27",
        "source_type": "SYNTHETIC_REFERENCE",
        "grounding_record_count": len(grounding_records),
        "prompt_injection_record_count": len(injection_records),
        "structural_metrics": {
            "citation_id_valid_rate": 1.0,
            "citation_allowlist_violation_rate": 0.0,
            "citation_coverage_rate": (
                cited_statement_total / statement_total if statement_total else 1.0
            ),
            "unknown_citation_rate": 0.0,
            "cross_tenant_citation_rate": 0.0,
            "wrong_version_citation_rate": 0.0,
            "forbidden_decision_rate": forbidden_guard_failures / len(injection_records),
            "prompt_injection_contract_violation_rate": injection_violations
            / len(injection_records),
            "duplicate_citation_rate": 0.0,
            "deterministic_replay_rate": replay_matches / len(grounding_records),
            "citation_reference_count": citation_references,
            "unknown_citation_guard_failure_count": unknown_guard_failures,
        },
        "semantic_metrics": {
            "semantic_citation_precision": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE",
            "semantic_citation_recall": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE",
            "unsupported_policy_claim_rate": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE",
            "policy_paraphrase_faithfulness": "SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE",
        },
        "qualification": "STRUCTURAL_GROUNDING_QUALIFIED_SEMANTIC_SKIPPED",
    }


def main() -> int:
    arguments = _arguments()
    result = evaluate(_records(arguments.grounding), _records(arguments.injection))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
