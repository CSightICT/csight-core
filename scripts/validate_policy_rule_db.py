"""Validate immutable rule, activation, source, and tenant invariants in PostgreSQL."""

import argparse
import json
from pathlib import Path

from sqlalchemy import String, and_, func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyClauseModel,
    PolicyRuleModel,
    PolicyRuleSetActivationModel,
    PolicyRuleSetModel,
    PolicyRuleSourceClauseModel,
)
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    with create_session_factory(get_engine(settings))() as session:
        rule_set_count = session.scalar(select(func.count(PolicyRuleSetModel.id))) or 0
        rule_count = session.scalar(select(func.count(PolicyRuleModel.id))) or 0
        source_count = session.scalar(select(func.count(PolicyRuleSourceClauseModel.id))) or 0
        active_count = (
            session.scalar(
                select(func.count(PolicyRuleSetActivationModel.id)).where(
                    PolicyRuleSetActivationModel.retired_at.is_(None)
                )
            )
            or 0
        )
        orphan_or_mismatch = (
            session.scalar(
                select(func.count(PolicyRuleSourceClauseModel.id))
                .select_from(PolicyRuleSourceClauseModel)
                .outerjoin(
                    PolicyClauseModel,
                    and_(
                        PolicyClauseModel.tenant_id == PolicyRuleSourceClauseModel.tenant_id,
                        PolicyClauseModel.id == PolicyRuleSourceClauseModel.policy_clause_row_id,
                        PolicyClauseModel.document_id == PolicyRuleSourceClauseModel.document_id,
                        PolicyClauseModel.document_version
                        == PolicyRuleSourceClauseModel.document_version,
                        PolicyClauseModel.clause_id == PolicyRuleSourceClauseModel.clause_id,
                        PolicyClauseModel.source_hash == PolicyRuleSourceClauseModel.source_hash,
                        PolicyClauseModel.document_status == "ACTIVE",
                    ),
                )
                .where(PolicyClauseModel.id.is_(None))
            )
            or 0
        )
        rules_without_sources = (
            session.scalar(
                select(func.count(PolicyRuleModel.id)).where(
                    ~select(PolicyRuleSourceClauseModel.id)
                    .where(
                        PolicyRuleSourceClauseModel.tenant_id == PolicyRuleModel.tenant_id,
                        PolicyRuleSourceClauseModel.policy_rule_id == PolicyRuleModel.id,
                    )
                    .exists()
                )
            )
            or 0
        )
        forbidden_effects = (
            session.scalar(
                select(func.count(PolicyRuleModel.id)).where(
                    PolicyRuleModel.effects.cast(String).op("~")(
                        "APPROVE|REJECT|FRAUD|LIABILITY|FINAL_DECISION"
                    )
                )
            )
            or 0
        )
    checks = {
        "rule_set_count": rule_set_count,
        "rule_count": rule_count,
        "source_clause_link_count": source_count,
        "active_rule_set_count": active_count,
        "orphan_cross_tenant_or_source_mismatch": orphan_or_mismatch,
        "rules_without_sources": rules_without_sources,
        "forbidden_final_decision_effects": forbidden_effects,
    }
    passed = checks == {
        "rule_set_count": 2,
        "rule_count": 24,
        "source_clause_link_count": 24,
        "active_rule_set_count": 2,
        "orphan_cross_tenant_or_source_mismatch": 0,
        "rules_without_sources": 0,
        "forbidden_final_decision_effects": 0,
    }
    print(json.dumps({**checks, "status": "PASS" if passed else "FAIL"}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
