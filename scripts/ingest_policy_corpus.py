"""Explicit local/test CLI for validated synthetic policy corpus ingestion."""

import argparse
import sys
from pathlib import Path

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_ingestion import ingest_validated_policy_corpus
from app.adapters.persistence.session import create_session_factory, session_scope
from app.bootstrap.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--corpus-root", type=Path, default=Path("data/policy_corpus"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    if settings.environment.strip().lower() not in {"local", "test"}:
        print("Synthetic policy ingestion is allowed only in local or test.", file=sys.stderr)
        return 2
    factory = create_session_factory(get_engine(settings))
    try:
        with session_scope(factory) as session:
            outcome = ingest_validated_policy_corpus(
                session=session,
                corpus_root=arguments.corpus_root,
                allow_synthetic_tenant_creation=True,
            )
    except Exception as error:
        print(f"POLICY_CORPUS_INGESTION_FAILED code={getattr(error, 'code', type(error).__name__)}")
        return 1
    print(
        "POLICY_CORPUS_INGESTED "
        f"run_id={outcome.run_id} reused={str(outcome.reused).lower()} "
        f"documents={outcome.document_count} clauses={outcome.clause_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
