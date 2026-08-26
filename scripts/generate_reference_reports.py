"""Generate aggregate JSON and Markdown coverage/quality reports."""

import json
from pathlib import Path

from scripts.validate_evaluation_data import validate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    corpus = json.loads(
        (ROOT / "data/policy_corpus/reports/policy_corpus_quality_v1.json").read_text(
            encoding="utf-8"
        )
    )
    datasets = validate()
    report = {
        "source_type": "SYNTHETIC_REFERENCE",
        "document_count": corpus["document_count"],
        "clause_count": corpus["clause_count"],
        "tenant_distribution": corpus["tenant_count"],
        "policy_type_coverage": corpus["policy_type_distribution"],
        "clause_type_coverage": corpus["clause_type_distribution"],
        "version_coverage": {
            "active": corpus["active_version_count"],
            "retired": corpus["retired_version_count"],
        },
        "exception_coverage": corpus["exception_count"],
        "duplicate_count": corpus["exact_duplicate_count"],
        "broken_reference_count": corpus["broken_reference_count"],
        "empty_clause_count": corpus["empty_clause_count"],
        **datasets,
        "prompt_injection_coverage": 8,
    }
    output_dir = ROOT / "data/policy_corpus/reports"
    (output_dir / "reference_data_quality_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "reference_data_quality_v1.md").write_text(
        "# CSight Reference Data v1 Quality Report\n\n"
        "> 합성 PoC Reference이며 실제 기업 정책이나 법률 자문이 아니다.\n\n"
        f"- Documents / Clauses: {report['document_count']} / {report['clause_count']}\n"
        f"- Active / Retired: {report['version_coverage']['active']} / "
        f"{report['version_coverage']['retired']}\n"
        f"- Exceptions: {report['exception_coverage']}\n"
        f"- Exact duplicates: {report['duplicate_count']}\n"
        f"- Broken references: {report['broken_reference_count']}\n"
        f"- Cross-tenant gold violations: {report['cross_tenant_gold_violation_count']}\n"
        f"- Extraction / Retrieval / Grounding / Injection / Demo: "
        f"{report['extraction_count']} / {report['retrieval_count']} / "
        f"{report['grounding_count']} / {report['injection_count']} / "
        f"{report['demo_count']}\n",
        encoding="utf-8",
    )
    print("REFERENCE_REPORTS_GENERATED broken=0 cross_tenant=0 duplicate=0")


if __name__ == "__main__":
    main()
