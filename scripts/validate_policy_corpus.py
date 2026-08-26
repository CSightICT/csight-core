"""Validate raw and generated policy corpus consistency without rebuilding source files."""

import json
from pathlib import Path

from app.platform.policy_reference import parse_document, validate_corpus


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "policy_corpus"
    documents = []
    clauses = []
    for path in sorted((root / "raw").glob("*/*.md")):
        document, parsed = parse_document(path, root=root)
        documents.append(document)
        clauses.extend(parsed)
    validate_corpus(tuple(documents), tuple(clauses))
    manifest = json.loads(
        (root / "manifests" / "policy_corpus_v1.json").read_text(encoding="utf-8")
    )
    if manifest["document_count"] != len(documents) or manifest["clause_count"] != len(clauses):
        raise ValueError("generated manifest counts differ from validated raw source")
    print(f"POLICY_CORPUS_VALID documents={len(documents)} clauses={len(clauses)}")


if __name__ == "__main__":
    main()
