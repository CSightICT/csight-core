"""Ingest validated immutable synthetic policy rule sets into local/test PostgreSQL."""

import argparse
import sys
from pathlib import Path

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings
from app.platform.policy_engine import PolicyRuleSet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("data/policy_rules/normalized/policy_rule_sets_v1.jsonl"),
    )
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    if settings.environment.strip().lower() not in {"local", "test"}:
        print("Synthetic policy rule ingestion is allowed only in local or test.", file=sys.stderr)
        return 2
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in arguments.rules.read_text(encoding="utf-8").splitlines()
        if line
    )
    try:
        inserted_sets, inserted_rules = SQLAlchemyPolicyEngineRepository(
            create_session_factory(get_engine(settings))
        ).ingest(rule_sets)
    except Exception as error:
        print(f"POLICY_RULE_INGESTION_FAILED code={getattr(error, 'code', type(error).__name__)}")
        return 1
    print(
        "POLICY_RULES_INGESTED "
        f"rule_sets_inserted={inserted_sets} rules_inserted={inserted_rules} "
        f"rule_sets_validated={len(rule_sets)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
