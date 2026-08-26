"""Build deterministic normalized policy documents, clauses, manifest, and reports."""

from pathlib import Path

from app.platform.policy_reference import build_corpus


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "policy_corpus"
    manifest = build_corpus(root)
    print(
        "POLICY_CORPUS_BUILT "
        f"documents={manifest['document_count']} clauses={manifest['clause_count']} "
        f"tenants={manifest['tenant_count']} hash={manifest['source_hash']}"
    )


if __name__ == "__main__":
    main()
