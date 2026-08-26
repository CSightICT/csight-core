"""Idempotently persist and activate the frozen Sprint 4C-1 execution profile."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyIndexVersionModel,
    PolicyRerankerProfileModel,
    PolicyRetrievalExecutionProfileModel,
)
from app.adapters.persistence.session import create_session_factory, session_scope
from app.bootstrap.settings import Settings
from app.platform.policy_retrieval import PolicyIndexStatus, stable_json_hash
from scripts.evaluate_policy_reranker import reranker_contract_hash

RESULT_ROOT = Path("evaluation/results/policy_reranker_v1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    profile_payload = json.loads(
        (RESULT_ROOT / "reranker_profile_v1.json").read_text(encoding="utf-8")
    )
    execution_payload = json.loads(
        (RESULT_ROOT / "retrieval_execution_profile_v2.json").read_text(encoding="utf-8")
    )
    if not profile_payload.get("test_evaluated"):
        raise ValueError("reranker Test evaluation must be locked before activation")
    if reranker_contract_hash(profile_payload) != profile_payload["profile_hash"]:
        raise ValueError("reranker profile hash mismatch")
    execution_contract = {
        key: value for key, value in execution_payload.items() if key != "profile_hash"
    }
    if stable_json_hash(execution_contract) != execution_payload["profile_hash"]:
        raise ValueError("execution profile hash mismatch")

    settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
    factory = create_session_factory(get_engine(settings))
    profile_id = uuid5(
        NAMESPACE_URL,
        f"csight:{profile_payload['profile_name']}:{profile_payload['profile_version']}",
    )
    created_profile = False
    created_executions = 0
    with session_scope(factory) as session:
        existing = session.get(PolicyRerankerProfileModel, profile_id)
        fields = {
            "profile_name": profile_payload["profile_name"],
            "profile_version": profile_payload["profile_version"],
            "provider_name": profile_payload["provider_name"],
            "model_artifact": profile_payload["model_artifact"],
            "model_revision": profile_payload["model_revision"],
            "instruction": profile_payload["instruction"],
            "instruction_hash": profile_payload["instruction_hash"],
            "query_template_name": profile_payload["query_template_name"],
            "query_template_version": profile_payload["query_template_version"],
            "query_template_hash": profile_payload["query_template_hash"],
            "document_template_name": profile_payload["document_template_name"],
            "document_template_version": profile_payload["document_template_version"],
            "document_template_hash": profile_payload["document_template_hash"],
            "max_query_tokens": profile_payload["max_query_tokens"],
            "max_document_tokens": profile_payload["max_document_tokens"],
            "max_pair_tokens": profile_payload["max_pair_tokens"],
            "candidate_k": profile_payload["candidate_k"],
            "final_k": profile_payload["final_k"],
            "batch_size": profile_payload["batch_size"],
            "device": profile_payload["device"],
            "score_semantics": profile_payload["score_semantics"],
        }
        if existing is None:
            session.add(PolicyRerankerProfileModel(id=profile_id, **fields))
            session.flush()
            created_profile = True
        elif any(getattr(existing, key) != value for key, value in fields.items()):
            raise ValueError("same reranker profile version has different content")

        indexes = tuple(
            session.scalars(
                select(PolicyIndexVersionModel).where(
                    PolicyIndexVersionModel.status == PolicyIndexStatus.ACTIVE.value,
                    PolicyIndexVersionModel.index_version
                    == execution_payload["base_index_version"],
                )
            )
        )
        if len(indexes) != 2:
            raise ValueError("expected one frozen ACTIVE base index for each of two tenants")
        for index in indexes:
            execution_id = uuid5(
                NAMESPACE_URL,
                f"csight:{execution_payload['profile_name']}:{execution_payload['profile_version']}:{index.id}",
            )
            existing_execution = session.get(PolicyRetrievalExecutionProfileModel, execution_id)
            execution_fields = {
                "profile_name": execution_payload["profile_name"],
                "profile_version": execution_payload["profile_version"],
                "base_index_version_id": index.id,
                "reranker_profile_id": profile_id,
                "candidate_mode": execution_payload["candidate_mode"],
                "candidate_k": execution_payload["candidate_k"],
                "final_k": execution_payload["final_k"],
                "status": execution_payload["status"],
                "profile_hash": execution_payload["profile_hash"],
            }
            if existing_execution is None:
                session.add(
                    PolicyRetrievalExecutionProfileModel(
                        id=execution_id,
                        activated_at=datetime.now(UTC),
                        retired_at=None,
                        **execution_fields,
                    )
                )
                created_executions += 1
            elif any(
                getattr(existing_execution, key) != value for key, value in execution_fields.items()
            ):
                raise ValueError("same execution profile version has different content")
    print(
        "POLICY_RERANKER_PROFILE_ACTIVE "
        f"profile_created={str(created_profile).lower()} "
        f"executions_created={created_executions} candidate_k={profile_payload['candidate_k']} "
        f"final_k={profile_payload['final_k']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
