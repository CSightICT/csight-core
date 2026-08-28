"""Prepare the existing ``csight`` tenant with a fictional synthetic policy runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    PolicyClauseEmbeddingModel,
    PolicyClauseModel,
    PolicyDocumentModel,
    PolicyIndexVersionModel,
    PolicyRuleModel,
    PolicyRuleSetActivationModel,
    PolicyRuleSetModel,
    PolicyRuleSourceClauseModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.adapters.persistence.policy_ingestion import ingest_validated_policy_corpus
from app.adapters.persistence.policy_repositories import to_policy_clause_record
from app.adapters.persistence.session import create_session_factory, session_scope
from app.bootstrap.settings import Settings
from app.platform.policy_engine import PolicyRuleSet, canonical_hash
from app.platform.policy_reference import (
    SYNTHETIC_DISCLAIMER,
    PolicyClause,
    PolicyDocument,
    parse_document,
    sha256_text,
)
from scripts.build_policy_embeddings import (
    INDEX_NAME,
    PROFILE_ID,
    CorpusIndexMetadata,
    build_policy_embeddings,
    embedding_snapshot,
    index_snapshot,
    validate_persisted_embedding_integrity,
    validate_protected_index_state,
)
from scripts.build_policy_embeddings import (
    INDEX_VERSION as LEGACY_INDEX_VERSION,
)

SOURCE_TENANT = "csight-demo-brand"
TARGET_TENANT = "csight"
DEFAULT_V2_POLICY_ROOT = Path(__file__).resolve().parents[1] / "data" / "csight_commerce_policy_v2"
EXPECTED_LEGACY_DOCUMENT_COUNT = 12
EXPECTED_LEGACY_CLAUSE_COUNT = 84
EXPECTED_LEGACY_RULE_COUNT = 12
EXPECTED_V2_DOCUMENT_COUNT = 8
EXPECTED_V2_CLAUSE_COUNT = 52
EXPECTED_V2_RULE_COUNT = 25
EXPECTED_DOCUMENT_COUNT = EXPECTED_LEGACY_DOCUMENT_COUNT + EXPECTED_V2_DOCUMENT_COUNT
EXPECTED_CLAUSE_COUNT = EXPECTED_LEGACY_CLAUSE_COUNT + EXPECTED_V2_CLAUSE_COUNT
EXPECTED_RULE_COUNT = EXPECTED_LEGACY_RULE_COUNT + EXPECTED_V2_RULE_COUNT
CORPUS_NAME = "csight_synthetic_policy_reference"
LEGACY_CORPUS_VERSION = "1.0.0-csight-demo"
CORPUS_VERSION = "2.0.0-csight-commerce-demo"
BUNDLE_VERSION = "2.0.1"
RULE_SET_NAME = "product_defect_policy"
LEGACY_RULE_SET_VERSION = "1.0.0"
POLICY_DOCUMENT_VERSION = "2.0.0"
FAULTY_RULE_SET_VERSION = "2.0.0"
RULE_SET_VERSION = "2.0.1"
INDEX_VERSION = "2.0.0"
FAULTY_RULE_SET_HISTORY_PATH = Path("policy_rules/history/policy_rule_set_2.0.0_noncanonical.json")
FAULTY_RULE_SET_SOURCE_PATH = Path("rules/history/policy_rule_set_2.0.0_noncanonical.json")


class PolicyRuntimePreparationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    root: Path
    corpus_root: Path
    corpus_manifest: Path
    rules_path: Path
    rules_manifest: Path
    corpus_source_hash: str
    rule_set_content_hash: str
    document_count: int
    clause_count: int
    rule_count: int
    reused: bool


@dataclass(frozen=True, slots=True)
class RuntimePreparationSummary:
    ingestion_reused: bool
    embedding_reused: int
    embedding_created: int
    rule_sets_inserted: int
    rules_inserted: int
    document_count: int
    clause_count: int
    embedding_count: int
    active_index_count: int
    active_rule_set_count: int
    rule_count: int
    source_link_count: int


def require_local_or_test(environment: str) -> None:
    if environment.strip().lower() not in {"local", "test"}:
        raise PolicyRuntimePreparationError(
            "ENVIRONMENT_NOT_ALLOWED",
            "Synthetic policy runtime preparation is allowed only in local or test.",
        )


def _require_loopback_http_url(value: str, *, label: str) -> str:
    normalized = value.rstrip("/")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError:
        raise PolicyRuntimePreparationError(
            "LOCAL_RUNTIME_URL_INVALID", f"{label} URL is invalid."
        ) from None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise PolicyRuntimePreparationError(
            "NON_LOOPBACK_RUNTIME_NOT_ALLOWED",
            f"{label} accepts only a loopback HTTP origin.",
        )
    return normalized


def require_local_runtime(
    *, environment: str, database_url: str | None, embedding_base_url: str
) -> str:
    """Reject non-local execution before materializing or mutating policy state."""

    require_local_or_test(environment)
    if not database_url:
        raise PolicyRuntimePreparationError("DATABASE_URL_MISSING", "DATABASE_URL is required.")
    try:
        database = make_url(database_url)
    except (TypeError, ValueError):
        raise PolicyRuntimePreparationError(
            "DATABASE_URL_INVALID", "DATABASE_URL is invalid."
        ) from None
    if not database.drivername.startswith("postgresql") or database.host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise PolicyRuntimePreparationError(
            "NON_LOOPBACK_DATABASE_NOT_ALLOWED",
            "Synthetic policy runtime preparation requires loopback PostgreSQL.",
        )
    return _require_loopback_http_url(embedding_base_url, label="Embedding")


def _json_line(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[union-attr]
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: tuple[object, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(_json_line(value) for value in values) + "\n", encoding="utf-8")


def _assert_document_derivation(source: PolicyDocument, target: PolicyDocument) -> None:
    source_payload = source.model_dump(
        mode="json", exclude={"tenant_id", "source_hash", "source_path"}
    )
    target_payload = target.model_dump(
        mode="json", exclude={"tenant_id", "source_hash", "source_path"}
    )
    if source_payload != target_payload or target.tenant_id != TARGET_TENANT:
        raise PolicyRuntimePreparationError(
            "DOCUMENT_DERIVATION_MISMATCH", "Target document differs beyond tenant-derived fields."
        )
    if source.source_type != "SYNTHETIC_REFERENCE" or target.source_type != "SYNTHETIC_REFERENCE":
        raise PolicyRuntimePreparationError(
            "NON_SYNTHETIC_SOURCE", "Every source and target document must be synthetic."
        )


def _assert_clause_derivation(source: PolicyClause, target: PolicyClause) -> None:
    excluded = {"tenant_id", "text", "source_hash", "content_hash"}
    if source.model_dump(mode="json", exclude=excluded) != target.model_dump(
        mode="json", exclude=excluded
    ):
        raise PolicyRuntimePreparationError(
            "CLAUSE_DERIVATION_MISMATCH", "Target clause differs beyond tenant-derived fields."
        )
    expected_text = source.text.replace(SOURCE_TENANT, TARGET_TENANT)
    if target.tenant_id != TARGET_TENANT or target.text != expected_text:
        raise PolicyRuntimePreparationError(
            "CLAUSE_TENANT_REWRITE_MISMATCH", "Target clause tenant text was not rewritten exactly."
        )
    if target.content_hash != sha256_text(target.text):
        raise PolicyRuntimePreparationError(
            "CLAUSE_CONTENT_HASH_MISMATCH", "Target clause content hash is invalid."
        )


def _materialize_into(
    *,
    source_corpus_root: Path,
    source_rules_path: Path,
    operations_v2_root: Path,
    target_root: Path,
) -> PolicyBundle:
    source_raw_root = source_corpus_root / "raw" / SOURCE_TENANT
    if not source_raw_root.is_dir() or source_raw_root.is_symlink():
        raise PolicyRuntimePreparationError(
            "SOURCE_CORPUS_MISSING", "The frozen fictional brand corpus is unavailable."
        )
    source_paths = tuple(sorted(source_raw_root.glob("*.md")))
    if len(source_paths) != EXPECTED_LEGACY_DOCUMENT_COUNT:
        raise PolicyRuntimePreparationError(
            "SOURCE_DOCUMENT_COUNT_MISMATCH", "The fictional brand document count changed."
        )
    if any(not path.is_file() or path.is_symlink() for path in source_paths):
        raise PolicyRuntimePreparationError(
            "SOURCE_DOCUMENT_UNSAFE", "Policy source paths must be regular non-symlink files."
        )

    corpus_root = target_root / "policy_corpus"
    target_raw_root = corpus_root / "raw" / TARGET_TENANT
    target_raw_root.mkdir(parents=True)
    documents: list[PolicyDocument] = []
    clauses: list[PolicyClause] = []
    source_clause_map: dict[str, PolicyClause] = {}
    for source_path in source_paths:
        source_raw = source_path.read_text(encoding="utf-8")
        if SOURCE_TENANT not in source_raw:
            raise PolicyRuntimePreparationError(
                "SOURCE_TENANT_MARKER_MISSING", "Source document lacks the expected tenant marker."
            )
        target_raw = source_raw.replace(SOURCE_TENANT, TARGET_TENANT)
        if SOURCE_TENANT in target_raw:
            raise PolicyRuntimePreparationError(
                "SOURCE_TENANT_REWRITE_INCOMPLETE", "Source tenant text remains after derivation."
            )
        target_path = target_raw_root / source_path.name
        target_path.write_text(target_raw, encoding="utf-8")
        source_document, source_clauses = parse_document(source_path, root=source_corpus_root)
        target_document, target_clauses = parse_document(target_path, root=corpus_root)
        _assert_document_derivation(source_document, target_document)
        if target_document.source_hash != sha256_text(unicodedata.normalize("NFC", target_raw)):
            raise PolicyRuntimePreparationError(
                "DOCUMENT_SOURCE_HASH_MISMATCH", "Target raw document hash is invalid."
            )
        if len(source_clauses) != len(target_clauses):
            raise PolicyRuntimePreparationError(
                "CLAUSE_COUNT_DERIVATION_MISMATCH", "Clause count changed during derivation."
            )
        for source_clause, target_clause in zip(source_clauses, target_clauses, strict=True):
            _assert_clause_derivation(source_clause, target_clause)
            if target_clause.source_hash != target_document.source_hash:
                raise PolicyRuntimePreparationError(
                    "CLAUSE_SOURCE_HASH_MISMATCH", "Clause source hash does not match raw document."
                )
            source_clause_map[source_clause.clause_id] = source_clause
        documents.append(target_document)
        clauses.extend(target_clauses)

    legacy_corpus_source_hash = sha256_text("".join(document.source_hash for document in documents))

    operations_raw_root = operations_v2_root / "raw" / TARGET_TENANT
    if not operations_raw_root.is_dir() or operations_raw_root.is_symlink():
        raise PolicyRuntimePreparationError(
            "V2_POLICY_CORPUS_MISSING", "The fictional CSight Commerce v2 corpus is unavailable."
        )
    operations_paths = tuple(sorted(operations_raw_root.glob("*.md")))
    if len(operations_paths) != EXPECTED_V2_DOCUMENT_COUNT:
        raise PolicyRuntimePreparationError(
            "V2_POLICY_DOCUMENT_COUNT_MISMATCH",
            "The fictional CSight Commerce v2 document count changed.",
        )
    if any(not path.is_file() or path.is_symlink() for path in operations_paths):
        raise PolicyRuntimePreparationError(
            "V2_POLICY_DOCUMENT_UNSAFE", "Policy v2 source paths must be regular files."
        )
    v2_clause_ids: set[str] = set()
    for operations_path in operations_paths:
        raw = operations_path.read_text(encoding="utf-8")
        if "실제 기업 정책이나 법률 자문" not in raw:
            raise PolicyRuntimePreparationError(
                "V2_POLICY_DISCLAIMER_MISSING",
                "Every fictional CSight Commerce v2 document requires the demo disclaimer.",
            )
        target_path = target_raw_root / operations_path.name
        if target_path.exists():
            raise PolicyRuntimePreparationError(
                "V2_POLICY_PATH_COLLISION", "A v2 policy source path collides with legacy data."
            )
        target_path.write_text(raw, encoding="utf-8")
        document, parsed_clauses = parse_document(target_path, root=corpus_root)
        if (
            document.tenant_id != TARGET_TENANT
            or document.document_version != POLICY_DOCUMENT_VERSION
            or document.source_type != "SYNTHETIC_REFERENCE"
            or document.status.value != "ACTIVE"
            or not document.document_id.startswith("CSC-OPS-")
        ):
            raise PolicyRuntimePreparationError(
                "V2_POLICY_IDENTITY_INVALID",
                "CSight Commerce v2 documents must be active, synthetic, and versioned 2.0.0.",
            )
        if document.source_hash != sha256_text(unicodedata.normalize("NFC", raw)):
            raise PolicyRuntimePreparationError(
                "V2_POLICY_SOURCE_HASH_MISMATCH", "A v2 policy source hash is invalid."
            )
        for clause in parsed_clauses:
            if clause.source_hash != document.source_hash:
                raise PolicyRuntimePreparationError(
                    "V2_POLICY_CLAUSE_HASH_MISMATCH",
                    "A v2 policy clause source hash does not match its document.",
                )
            v2_clause_ids.add(clause.clause_id)
        documents.append(document)
        clauses.extend(parsed_clauses)

    if len(v2_clause_ids) != EXPECTED_V2_CLAUSE_COUNT:
        raise PolicyRuntimePreparationError(
            "V2_POLICY_CLAUSE_COUNT_MISMATCH",
            "The fictional CSight Commerce v2 clause count changed.",
        )

    if len(documents) != EXPECTED_DOCUMENT_COUNT or len(clauses) != EXPECTED_CLAUSE_COUNT:
        raise PolicyRuntimePreparationError(
            "TARGET_CORPUS_COUNT_MISMATCH", "Derived corpus document or clause count is invalid."
        )
    if len({(item.document_id, item.document_version) for item in documents}) != len(documents):
        raise PolicyRuntimePreparationError(
            "TARGET_DOCUMENT_IDENTITY_DUPLICATE", "Derived document identities are not unique."
        )
    if len({item.clause_id for item in clauses}) != len(clauses):
        raise PolicyRuntimePreparationError(
            "TARGET_CLAUSE_IDENTITY_DUPLICATE", "Derived clause identities are not unique."
        )
    clause_map = {item.clause_id: item for item in clauses}
    for clause in clauses:
        if clause.parent_clause_id:
            parent = clause_map.get(clause.parent_clause_id)
            if (
                parent is None
                or parent.document_id != clause.document_id
                or parent.document_version != clause.document_version
            ):
                raise PolicyRuntimePreparationError(
                    "TARGET_PARENT_REFERENCE_INVALID", "Derived parent-clause reference is invalid."
                )

    corpus_source_hash = sha256_text("".join(document.source_hash for document in documents))
    clause_types = Counter(item.clause_type.value for item in clauses)
    policy_types = Counter(item.policy_type for item in documents)
    corpus_manifest_payload = {
        "active_version_count": sum(item.status.value == "ACTIVE" for item in documents),
        "builder_version": BUNDLE_VERSION,
        "clause_count": len(clauses),
        "clause_type_distribution": dict(sorted(clause_types.items())),
        "corpus_name": CORPUS_NAME,
        "corpus_version": CORPUS_VERSION,
        "created_at": "2026-08-28T00:00:00Z",
        "disclaimer": SYNTHETIC_DISCLAIMER,
        "document_count": len(documents),
        "exact_duplicate_count": len(clauses) - len({item.content_hash for item in clauses}),
        "policy_type_distribution": dict(sorted(policy_types.items())),
        "retired_version_count": sum(item.status.value == "RETIRED" for item in documents),
        "schema_version": "1.0",
        "source_hash": corpus_source_hash,
        "source_type": "SYNTHETIC_REFERENCE",
        "tenant_count": 1,
    }
    documents_path = corpus_root / "normalized" / "policy_documents_v1.jsonl"
    clauses_path = corpus_root / "clauses" / "policy_clauses_v1.jsonl"
    corpus_manifest = corpus_root / "manifests" / "policy_corpus_v1.json"
    _write_jsonl(documents_path, tuple(documents))
    _write_jsonl(clauses_path, tuple(clauses))
    _write_json(corpus_manifest, corpus_manifest_payload)
    _write_json(
        corpus_root / "reports" / "policy_corpus_quality_v1.json",
        {
            **corpus_manifest_payload,
            "broken_reference_count": 0,
            "empty_clause_count": 0,
            "target_tenant": TARGET_TENANT,
        },
    )

    source_rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in source_rules_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    matching = tuple(item for item in source_rule_sets if item.tenant_slug == SOURCE_TENANT)
    if len(matching) != 1 or len(matching[0].rules) != EXPECTED_LEGACY_RULE_COUNT:
        raise PolicyRuntimePreparationError(
            "SOURCE_RULE_SET_MISMATCH", "The frozen fictional brand rule set changed."
        )
    source_rule_set = matching[0]
    source_manifest = json.loads(
        (source_corpus_root / "manifests" / "policy_corpus_v1.json").read_text(encoding="utf-8")
    )
    if source_manifest.get(
        "source_type"
    ) != "SYNTHETIC_REFERENCE" or source_rule_set.source_corpus_hash != source_manifest.get(
        "source_hash"
    ):
        raise PolicyRuntimePreparationError(
            "SOURCE_RULE_CORPUS_HASH_MISMATCH",
            "The fictional source rule set does not match its source corpus manifest.",
        )
    legacy_rule_payload = source_rule_set.model_dump(mode="json")
    legacy_rule_payload["tenant_slug"] = TARGET_TENANT
    legacy_rule_payload["source_corpus_name"] = CORPUS_NAME
    legacy_rule_payload["source_corpus_version"] = LEGACY_CORPUS_VERSION
    legacy_rule_payload["source_corpus_hash"] = legacy_corpus_source_hash
    for rule in legacy_rule_payload["rules"]:
        for source in rule["source_references"]:
            original_clause = source_clause_map.get(source["clause_id"])
            clause = clause_map.get(source["clause_id"])
            if (
                original_clause is None
                or clause is None
                or original_clause.document_status.value != "ACTIVE"
                or original_clause.document_id != source["document_id"]
                or original_clause.document_version != source["document_version"]
                or original_clause.source_hash != source["source_hash"]
                or clause.document_status.value != "ACTIVE"
                or clause.document_id != source["document_id"]
                or clause.document_version != source["document_version"]
            ):
                raise PolicyRuntimePreparationError(
                    "RULE_SOURCE_REFERENCE_INVALID",
                    "A rule source does not match an active clause.",
                )
            source["source_hash"] = clause.source_hash
    legacy_rule_set = PolicyRuleSet.model_validate(legacy_rule_payload)
    if legacy_rule_set.rule_set_version != LEGACY_RULE_SET_VERSION:
        raise PolicyRuntimePreparationError(
            "LEGACY_RULE_SET_VERSION_MISMATCH", "The preserved legacy rule-set version changed."
        )

    blueprint_path = operations_v2_root / "rules" / "policy_rule_set_v2.json"
    if not blueprint_path.is_file() or blueprint_path.is_symlink():
        raise PolicyRuntimePreparationError(
            "V2_RULE_BLUEPRINT_MISSING", "The fictional CSight Commerce v2 rules are unavailable."
        )
    v2_payload = json.loads(blueprint_path.read_text(encoding="utf-8"))
    if not isinstance(v2_payload, dict):
        raise PolicyRuntimePreparationError(
            "V2_RULE_BLUEPRINT_INVALID", "The v2 rule blueprint must be a JSON object."
        )
    if (
        v2_payload.get("tenant_slug") != TARGET_TENANT
        or v2_payload.get("rule_set_name") != RULE_SET_NAME
        or v2_payload.get("rule_set_version") != RULE_SET_VERSION
        or v2_payload.get("source_type") != "SYNTHETIC_REFERENCE"
    ):
        raise PolicyRuntimePreparationError(
            "V2_RULE_IDENTITY_INVALID", "The v2 rule blueprint identity is invalid."
        )
    blueprint_rules = v2_payload.get("rules")
    if not isinstance(blueprint_rules, list) or len(blueprint_rules) != EXPECTED_V2_RULE_COUNT:
        raise PolicyRuntimePreparationError(
            "V2_RULE_COUNT_MISMATCH", "The fictional CSight Commerce v2 rule count changed."
        )
    history_path = operations_v2_root / FAULTY_RULE_SET_SOURCE_PATH
    if not history_path.is_file() or history_path.is_symlink():
        raise PolicyRuntimePreparationError(
            "V2_FAULTY_HISTORY_MISSING",
            "The frozen known-faulty 2.0.0 history fixture is unavailable.",
        )
    history_payload = json.loads(history_path.read_text(encoding="utf-8"))
    if (
        not isinstance(history_payload, dict)
        or history_payload.get("schema_version") != "1.0.0"
        or history_payload.get("rule_set_name") != RULE_SET_NAME
        or history_payload.get("rule_set_version") != FAULTY_RULE_SET_VERSION
        or not isinstance(history_payload.get("expected_content_hash"), str)
        or not isinstance(history_payload.get("source_clause_order_overrides"), dict)
    ):
        raise PolicyRuntimePreparationError(
            "V2_FAULTY_HISTORY_INVALID",
            "The frozen known-faulty 2.0.0 history fixture is invalid.",
        )
    expected_faulty_hash = str(history_payload["expected_content_hash"])
    faulty_order_overrides = history_payload["source_clause_order_overrides"]
    assert isinstance(faulty_order_overrides, dict)
    if len(expected_faulty_hash) != 64 or any(
        character not in "0123456789abcdef" for character in expected_faulty_hash
    ):
        raise PolicyRuntimePreparationError(
            "V2_FAULTY_HISTORY_INVALID", "The known-faulty content hash is invalid."
        )

    rule_identities = tuple(
        (str(item.get("rule_id")), str(item.get("rule_version")))
        for item in blueprint_rules
        if isinstance(item, dict)
    )
    if len(rule_identities) != len(blueprint_rules) or rule_identities != tuple(
        sorted(rule_identities)
    ):
        raise PolicyRuntimePreparationError(
            "V2_RULE_ORDER_INVALID", "The active v2 blueprint rules must be canonical."
        )

    faulty_materialized_rules: list[dict[str, object]] = []
    fixed_materialized_rules: list[dict[str, object]] = []
    used_faulty_overrides: set[str] = set()
    for blueprint_rule in blueprint_rules:
        if not isinstance(blueprint_rule, dict):
            raise PolicyRuntimePreparationError(
                "V2_RULE_BLUEPRINT_INVALID", "Every v2 rule blueprint entry must be an object."
            )
        fixed_rule = dict(blueprint_rule)
        if fixed_rule.get("rule_version") != RULE_SET_VERSION:
            raise PolicyRuntimePreparationError(
                "V2_RULE_VERSION_INVALID",
                "Every active v2 blueprint rule must use version 2.0.1.",
            )
        rule_id = str(fixed_rule["rule_id"])
        source_clause_ids = fixed_rule.pop("source_clause_ids", None)
        if (
            not isinstance(source_clause_ids, list)
            or not source_clause_ids
            or not all(isinstance(item, str) and item for item in source_clause_ids)
            or len(source_clause_ids) != len(set(source_clause_ids))
        ):
            raise PolicyRuntimePreparationError(
                "V2_RULE_SOURCE_IDS_INVALID", "Every v2 rule needs unique source clause IDs."
            )
        if source_clause_ids != sorted(source_clause_ids):
            raise PolicyRuntimePreparationError(
                "V2_RULE_SOURCE_ORDER_INVALID",
                "Every active v2 rule must declare source clauses in canonical order.",
            )
        source_references: list[dict[str, str]] = []
        for clause_id in source_clause_ids:
            clause = clause_map.get(clause_id)
            if (
                clause is None
                or clause_id not in v2_clause_ids
                or clause.document_status.value != "ACTIVE"
                or clause.document_version != POLICY_DOCUMENT_VERSION
            ):
                raise PolicyRuntimePreparationError(
                    "V2_RULE_SOURCE_REFERENCE_INVALID",
                    "A v2 rule source must match an active immutable v2 clause.",
                )
            source_references.append(
                {
                    "clause_id": clause.clause_id,
                    "document_id": clause.document_id,
                    "document_version": clause.document_version,
                    "source_hash": clause.source_hash,
                }
            )
        fixed_rule["source_references"] = source_references
        override = faulty_order_overrides.get(rule_id, source_clause_ids)
        if (
            not isinstance(override, list)
            or not all(isinstance(item, str) for item in override)
            or sorted(override) != source_clause_ids
        ):
            raise PolicyRuntimePreparationError(
                "V2_FAULTY_HISTORY_INVALID",
                "A known-faulty source-order override is not an exact rule-source permutation.",
            )
        if rule_id in faulty_order_overrides:
            used_faulty_overrides.add(rule_id)
        source_references_by_clause = {str(item["clause_id"]): item for item in source_references}
        faulty_rule = dict(fixed_rule)
        faulty_rule["rule_version"] = FAULTY_RULE_SET_VERSION
        faulty_rule["source_references"] = [
            source_references_by_clause[clause_id] for clause_id in override
        ]
        faulty_materialized_rules.append(faulty_rule)
        fixed_materialized_rules.append(fixed_rule)
    if used_faulty_overrides != set(faulty_order_overrides):
        raise PolicyRuntimePreparationError(
            "V2_FAULTY_HISTORY_INVALID",
            "The known-faulty history fixture contains an unknown rule identity.",
        )

    fixed_v2_payload = dict(v2_payload)
    fixed_v2_payload["source_corpus_name"] = CORPUS_NAME
    fixed_v2_payload["source_corpus_version"] = CORPUS_VERSION
    fixed_v2_payload["source_corpus_hash"] = corpus_source_hash
    fixed_v2_payload["rules"] = fixed_materialized_rules
    v2_rule_set = PolicyRuleSet.model_validate(fixed_v2_payload)

    faulty_v2_payload = dict(fixed_v2_payload)
    faulty_v2_payload["rule_set_version"] = FAULTY_RULE_SET_VERSION
    faulty_v2_payload["source_corpus_name"] = CORPUS_NAME
    faulty_v2_payload["source_corpus_version"] = CORPUS_VERSION
    faulty_v2_payload["source_corpus_hash"] = corpus_source_hash
    faulty_v2_payload["rules"] = faulty_materialized_rules
    faulty_v2_rule_set = PolicyRuleSet.model_validate(faulty_v2_payload)
    if faulty_v2_rule_set.content_hash != expected_faulty_hash:
        raise PolicyRuntimePreparationError(
            "V2_FAULTY_HISTORY_HASH_MISMATCH",
            "The known-faulty 2.0.0 rule-set history no longer matches its frozen hash.",
        )
    if (
        any(not rule.prohibit_final_decision for rule in v2_rule_set.rules)
        or any(not rule.requires_human_review for rule in v2_rule_set.rules)
        or any(
            not any(effect.type.value == "REQUIRE_HUMAN_REVIEW" for effect in rule.effects)
            and not any(effect.type.value == "REQUIRE_MANAGER_REVIEW" for effect in rule.effects)
            for rule in v2_rule_set.rules
        )
    ):
        raise PolicyRuntimePreparationError(
            "V2_RULE_ADVISORY_BOUNDARY_INVALID",
            "Every v2 rule must preserve the authenticated human decision boundary.",
        )
    target_rule_sets = (legacy_rule_set, v2_rule_set)
    rules_root = target_root / "policy_rules"
    rules_path = rules_root / "normalized" / "policy_rule_sets_v1.jsonl"
    rules_manifest = rules_root / "manifests" / "policy_rule_sets_v1.json"
    _write_jsonl(rules_path, target_rule_sets)
    _write_json(
        target_root / FAULTY_RULE_SET_HISTORY_PATH,
        faulty_v2_rule_set.model_dump(mode="json"),
    )
    rule_manifest_payload = {
        "builder_version": BUNDLE_VERSION,
        "active_rule_set_version": RULE_SET_VERSION,
        "content_hash": canonical_hash([item.model_dump(mode="json") for item in target_rule_sets]),
        "dataset": "policy_rule_sets_v1",
        "known_faulty_history_content_hash": faulty_v2_rule_set.content_hash,
        "known_faulty_history_version": FAULTY_RULE_SET_VERSION,
        "rule_count": sum(len(item.rules) for item in target_rule_sets),
        "rule_set_count": len(target_rule_sets),
        "schema_version": "1.0.0",
        "source_clause_count": sum(
            len(rule.source_references) for item in target_rule_sets for rule in item.rules
        ),
        "source_type": "SYNTHETIC_REFERENCE",
        "tenant_count": 1,
    }
    _write_json(rules_manifest, rule_manifest_payload)
    _write_json(
        target_root / "bundle_manifest.json",
        {
            "bundle_version": BUNDLE_VERSION,
            "clause_count": len(clauses),
            "corpus_source_hash": corpus_source_hash,
            "document_count": len(documents),
            "policy_authority": "FICTIONAL_DEMO_ONLY",
            "active_index_version": INDEX_VERSION,
            "active_rule_set_version": RULE_SET_VERSION,
            "legacy_rule_set_version": LEGACY_RULE_SET_VERSION,
            "known_faulty_rule_set_content_hash": faulty_v2_rule_set.content_hash,
            "known_faulty_rule_set_version": FAULTY_RULE_SET_VERSION,
            "rule_count": sum(len(item.rules) for item in target_rule_sets),
            "rule_set_content_hash": v2_rule_set.content_hash,
            "source_type": "SYNTHETIC_REFERENCE",
            "target_tenant": TARGET_TENANT,
        },
    )
    (target_root / "README.md").write_text(
        "# CSight Commerce Synthetic Policy Runtime Bundle v2\n\n"
        "> 이 번들은 데모 동작 검증용 완전 가상 사내 운영규정이며 실제 기업 정책, "
        "약관, 운영 관행 또는 법률 자문을 복제하거나 주장하지 않는다.\n\n"
        "- Target tenant: `csight`\n"
        "- Source type: `SYNTHETIC_REFERENCE`\n"
        "- Policy authority: `FICTIONAL_DEMO_ONLY`\n"
        "- Preserved rule set: `product_defect_policy/1.0.0`\n"
        "- Policy documents and retrieval index: `2.0.0`\n"
        "- Known faulty rule-set history: `product_defect_policy/2.0.0` "
        "(never ingested on a clean install)\n"
        "- Active rule set: `product_defect_policy/2.0.1`\n"
        "- Decision boundary: advisory effects only; authenticated human review is final.\n",
        encoding="utf-8",
    )
    return PolicyBundle(
        root=target_root,
        corpus_root=corpus_root,
        corpus_manifest=corpus_manifest,
        rules_path=rules_path,
        rules_manifest=rules_manifest,
        corpus_source_hash=corpus_source_hash,
        rule_set_content_hash=v2_rule_set.content_hash,
        document_count=len(documents),
        clause_count=len(clauses),
        rule_count=sum(len(item.rules) for item in target_rule_sets),
        reused=False,
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise PolicyRuntimePreparationError(
            "OUTPUT_PATH_UNSAFE", "The policy bundle output must be a regular directory."
        )
    files = tuple(sorted(root.rglob("*")))
    if any(path.is_symlink() for path in files):
        raise PolicyRuntimePreparationError(
            "OUTPUT_PATH_UNSAFE", "The policy bundle may not contain symlinks."
        )
    return {str(path.relative_to(root)): path.read_bytes() for path in files if path.is_file()}


def _load_bundle(root: Path, *, reused: bool) -> PolicyBundle:
    corpus_manifest_path = root / "policy_corpus" / "manifests" / "policy_corpus_v1.json"
    rules_path = root / "policy_rules" / "normalized" / "policy_rule_sets_v1.jsonl"
    rules_manifest = root / "policy_rules" / "manifests" / "policy_rule_sets_v1.json"
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in rules_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    active_rule_set = next(
        (item for item in rule_sets if item.rule_set_version == RULE_SET_VERSION), None
    )
    if active_rule_set is None or len(rule_sets) != 2:
        raise PolicyRuntimePreparationError(
            "BUNDLE_RULE_SET_COUNT_MISMATCH",
            "Derived v2 bundle must contain preserved v1 and active v2 rule sets.",
        )
    return PolicyBundle(
        root=root,
        corpus_root=root / "policy_corpus",
        corpus_manifest=corpus_manifest_path,
        rules_path=rules_path,
        rules_manifest=rules_manifest,
        corpus_source_hash=str(corpus_manifest["source_hash"]),
        rule_set_content_hash=active_rule_set.content_hash,
        document_count=int(corpus_manifest["document_count"]),
        clause_count=int(corpus_manifest["clause_count"]),
        rule_count=sum(len(item.rules) for item in rule_sets),
        reused=reused,
    )


def materialize_policy_bundle(
    *,
    source_corpus_root: Path,
    source_rules_path: Path,
    output_root: Path,
    operations_v2_root: Path = DEFAULT_V2_POLICY_ROOT,
) -> PolicyBundle:
    """Materialize an atomic deterministic bundle without overwriting a mismatched output."""

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".csight-policy-", dir=output_root.parent))
    try:
        _materialize_into(
            source_corpus_root=source_corpus_root,
            source_rules_path=source_rules_path,
            operations_v2_root=operations_v2_root,
            target_root=temporary,
        )
        if output_root.exists():
            if _tree_bytes(output_root) != _tree_bytes(temporary):
                raise PolicyRuntimePreparationError(
                    "OUTPUT_CONTENT_MISMATCH",
                    "Existing derived bundle differs; it was left unchanged.",
                )
            return _load_bundle(output_root, reused=True)
        temporary.replace(output_root)
        return _load_bundle(output_root, reused=False)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _rule_sets_from_bundle(bundle: PolicyBundle) -> tuple[PolicyRuleSet, ...]:
    lines = [line for line in bundle.rules_path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 2:
        raise PolicyRuntimePreparationError(
            "BUNDLE_RULE_SET_COUNT_MISMATCH",
            "Derived v2 bundle must contain preserved v1 and active v2 rule sets.",
        )
    rule_sets = tuple(PolicyRuleSet.model_validate_json(line) for line in lines)
    if {item.rule_set_version for item in rule_sets} != {
        LEGACY_RULE_SET_VERSION,
        RULE_SET_VERSION,
    } or any(item.rule_set_name != RULE_SET_NAME for item in rule_sets):
        raise PolicyRuntimePreparationError(
            "BUNDLE_RULE_SET_IDENTITY_MISMATCH", "Derived bundle rule-set identities are invalid."
        )
    return rule_sets


def _faulty_rule_set_from_bundle(bundle: PolicyBundle) -> PolicyRuleSet:
    path = bundle.root / FAULTY_RULE_SET_HISTORY_PATH
    if not path.is_file() or path.is_symlink():
        raise PolicyRuntimePreparationError(
            "BUNDLE_FAULTY_HISTORY_MISSING",
            "The known faulty 2.0.0 rule-set audit artifact is missing.",
        )
    value = PolicyRuleSet.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        value.tenant_slug != TARGET_TENANT
        or value.rule_set_name != RULE_SET_NAME
        or value.rule_set_version != FAULTY_RULE_SET_VERSION
        or len(value.rules) != EXPECTED_V2_RULE_COUNT
    ):
        raise PolicyRuntimePreparationError(
            "BUNDLE_FAULTY_HISTORY_INVALID",
            "The known faulty 2.0.0 rule-set audit artifact is invalid.",
        )
    return value


def _validate_index_state(
    index: PolicyIndexVersionModel,
    *,
    metadata: CorpusIndexMetadata,
    expected_clause_count: int,
    index_version: str,
    expected_status: str,
) -> None:
    snapshot = index_snapshot(index)
    validate_protected_index_state(
        replace(snapshot, status="ACTIVE", retired_at=None),
        metadata=metadata,
        expected_clause_count=expected_clause_count,
        index_name=INDEX_NAME,
        index_version=index_version,
    )
    if expected_status == "ACTIVE":
        if snapshot.status != "ACTIVE" or snapshot.retired_at is not None:
            raise ValueError("target policy index is not the expected ACTIVE version")
    elif expected_status == "RETIRED":
        if snapshot.status != "RETIRED" or snapshot.retired_at is None:
            raise ValueError("preserved legacy policy index is not cleanly RETIRED")
    else:
        raise AssertionError("unsupported expected index state")


def _version_reference(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    document_id, separator, version = value.partition("@")
    if not separator or not document_id or not version:
        raise PolicyRuntimePreparationError(
            "BUNDLE_DOCUMENT_REFERENCE_INVALID", "Derived document version reference is invalid."
        )
    return document_id, version


def _expected_document_state(document: PolicyDocument) -> tuple[object, ...]:
    supersedes = _version_reference(document.supersedes)
    superseded_by = _version_reference(document.superseded_by)
    return (
        document.document_id,
        document.document_version,
        document.title,
        document.policy_type,
        document.authority_level,
        document.product_categories,
        document.effective_from,
        document.effective_to,
        document.status.value,
        document.source_type,
        document.source_hash,
        *supersedes,
        *superseded_by,
    )


def _persisted_document_state(document: PolicyDocumentModel) -> tuple[object, ...]:
    return (
        document.document_id,
        document.document_version,
        document.title,
        document.policy_type,
        document.authority_level,
        tuple(document.product_categories),
        document.effective_from,
        document.effective_to,
        document.document_status,
        document.source_type,
        document.source_hash,
        document.supersedes_document_id,
        document.supersedes_document_version,
        document.superseded_by_document_id,
        document.superseded_by_document_version,
    )


def _expected_clause_state(clause: PolicyClause, *, document: PolicyDocument) -> tuple[object, ...]:
    return (
        clause.document_id,
        clause.document_version,
        document.title,
        clause.clause_id,
        clause.section_path,
        clause.clause_type.value,
        clause.text,
        clause.parent_clause_id,
        clause.policy_type,
        clause.product_categories,
        clause.defect_types,
        clause.actions,
        clause.requires_human_review,
        clause.effective_from,
        clause.effective_to,
        clause.document_status.value,
        clause.source_type,
        clause.source_hash,
        clause.content_hash,
    )


def _persisted_clause_state(clause: PolicyClauseModel) -> tuple[object, ...]:
    return (
        clause.document_id,
        clause.document_version,
        clause.title,
        clause.clause_id,
        tuple(clause.section_path),
        clause.clause_type,
        clause.text,
        clause.parent_clause_id,
        clause.policy_type,
        tuple(clause.product_categories),
        tuple(clause.defect_types),
        tuple(clause.actions),
        clause.requires_human_review,
        clause.effective_from,
        clause.effective_to,
        clause.document_status,
        clause.source_type,
        clause.source_hash,
        clause.content_hash,
    )


def validate_persisted_policy_semantics(
    *,
    documents: tuple[PolicyDocument, ...],
    clauses: tuple[PolicyClause, ...],
    persisted_documents: tuple[PolicyDocumentModel, ...],
    persisted_clauses: tuple[PolicyClauseModel, ...],
    require_complete: bool,
) -> None:
    """Compare all persisted retrieval semantics, not only content hashes."""

    expected_documents = {(item.document_id, item.document_version): item for item in documents}
    actual_documents = {
        (item.document_id, item.document_version): item for item in persisted_documents
    }
    if len(actual_documents) != len(persisted_documents):
        raise PolicyRuntimePreparationError(
            "TARGET_DOCUMENT_STATE_CONFLICT", "Target policy document identities are duplicated."
        )
    for key, row in actual_documents.items():
        expected = expected_documents.get(key)
        if expected is None or _persisted_document_state(row) != _expected_document_state(expected):
            raise PolicyRuntimePreparationError(
                "TARGET_DOCUMENT_STATE_CONFLICT",
                "Existing target policy document semantics differ from the derived bundle.",
            )
    expected_clauses = {
        (item.document_id, item.document_version, item.clause_id): item for item in clauses
    }
    actual_clauses = {
        (item.document_id, item.document_version, item.clause_id): item
        for item in persisted_clauses
    }
    if len(actual_clauses) != len(persisted_clauses):
        raise PolicyRuntimePreparationError(
            "TARGET_CLAUSE_STATE_CONFLICT", "Target policy clause identities are duplicated."
        )
    for key, row in actual_clauses.items():
        expected = expected_clauses.get(key)
        expected_document = expected_documents.get((row.document_id, row.document_version))
        actual_document = actual_documents.get((row.document_id, row.document_version))
        if (
            expected is None
            or expected_document is None
            or actual_document is None
            or row.document_row_id != actual_document.id
            or _persisted_clause_state(row)
            != _expected_clause_state(expected, document=expected_document)
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_CLAUSE_STATE_CONFLICT",
                "Existing target policy clause semantics differ from the derived bundle.",
            )
    if require_complete and (
        set(actual_documents) != set(expected_documents)
        or set(actual_clauses) != set(expected_clauses)
    ):
        raise PolicyRuntimePreparationError(
            "TARGET_POLICY_STATE_INCOMPLETE",
            "Persisted target policy documents or clauses are incomplete.",
        )


def validate_persisted_rule_semantics(
    *,
    expected_rule_sets: tuple[PolicyRuleSet, ...],
    persisted_rule_sets: tuple[PolicyRuleSetModel, ...],
    persisted_rules: tuple[PolicyRuleModel, ...],
    persisted_source_links: tuple[PolicyRuleSourceClauseModel, ...],
    persisted_clauses: tuple[PolicyClauseModel, ...],
    require_complete: bool,
) -> None:
    """Fail closed on any immutable rule, effect, or source-link drift."""

    expected_sets_by_version = {item.rule_set_version: item for item in expected_rule_sets}
    actual_sets_by_version = {item.rule_set_version: item for item in persisted_rule_sets}
    if len(actual_sets_by_version) != len(persisted_rule_sets) or any(
        version not in expected_sets_by_version for version in actual_sets_by_version
    ):
        raise PolicyRuntimePreparationError(
            "TARGET_RULE_SET_STATE_CONFLICT",
            "Persisted target rule-set identities are outside the immutable bundle.",
        )
    if require_complete and set(actual_sets_by_version) != set(expected_sets_by_version):
        raise PolicyRuntimePreparationError(
            "TARGET_RULE_SET_STATE_INCOMPLETE",
            "The immutable v1/v2 rule-set history is incomplete.",
        )
    set_ids = {item.id for item in persisted_rule_sets}
    if any(item.rule_set_id not in set_ids for item in persisted_rules):
        raise PolicyRuntimePreparationError(
            "TARGET_RULE_STATE_CONFLICT", "A persisted rule belongs to an unexpected rule set."
        )
    rule_ids = {item.id for item in persisted_rules}
    if any(item.policy_rule_id not in rule_ids for item in persisted_source_links):
        raise PolicyRuntimePreparationError(
            "TARGET_RULE_SOURCE_STATE_CONFLICT",
            "A persisted rule source belongs to an unexpected rule.",
        )
    clauses_by_id = {item.clause_id: item for item in persisted_clauses}
    if len(clauses_by_id) != len(persisted_clauses):
        raise PolicyRuntimePreparationError(
            "TARGET_RULE_SOURCE_STATE_CONFLICT", "Persisted clause IDs are not unique."
        )
    for version, row in actual_sets_by_version.items():
        expected_set = expected_sets_by_version[version]
        if (
            row.rule_set_name != expected_set.rule_set_name
            or row.effective_from != expected_set.effective_from
            or row.effective_to != expected_set.effective_to
            or row.source_corpus_name != expected_set.source_corpus_name
            or row.source_corpus_version != expected_set.source_corpus_version
            or row.source_corpus_hash != expected_set.source_corpus_hash
            or row.source_type != expected_set.source_type
            or row.rule_schema_version != expected_set.rule_schema_version
            or row.field_registry_version != expected_set.field_registry_version
            or row.operator_registry_version != expected_set.operator_registry_version
            or row.aggregation_version != expected_set.aggregation_version
            or row.content_hash != expected_set.content_hash
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_RULE_SET_STATE_CONFLICT",
                "A persisted rule set differs from its immutable bundle version.",
            )
        expected_rules = {(item.rule_id, item.rule_version): item for item in expected_set.rules}
        actual_rules = {
            (item.rule_id, item.rule_version): item
            for item in persisted_rules
            if item.rule_set_id == row.id
        }
        if set(actual_rules) != set(expected_rules):
            raise PolicyRuntimePreparationError(
                "TARGET_RULE_STATE_CONFLICT", "Persisted typed-rule identities are incomplete."
            )
        for identity, rule_row in actual_rules.items():
            expected_rule = expected_rules[identity]
            if (
                rule_row.category != expected_rule.category.value
                or rule_row.priority != expected_rule.priority
                or rule_row.conditions
                != [item.model_dump(mode="json") for item in expected_rule.conditions]
                or rule_row.effects
                != [item.model_dump(mode="json") for item in expected_rule.effects]
                or rule_row.requires_human_review != expected_rule.requires_human_review
                or rule_row.prohibit_final_decision != expected_rule.prohibit_final_decision
                or rule_row.content_hash != expected_rule.content_hash
            ):
                raise PolicyRuntimePreparationError(
                    "TARGET_RULE_STATE_CONFLICT",
                    "A persisted typed rule differs from its immutable bundle version.",
                )
            actual_links = {
                (
                    item.clause_id,
                    item.document_id,
                    item.document_version,
                    item.source_hash,
                    item.policy_clause_row_id,
                )
                for item in persisted_source_links
                if item.policy_rule_id == rule_row.id
            }
            try:
                expected_links = {
                    (
                        item.clause_id,
                        item.document_id,
                        item.document_version,
                        item.source_hash,
                        clauses_by_id[item.clause_id].id,
                    )
                    for item in expected_rule.source_references
                }
            except KeyError:
                raise PolicyRuntimePreparationError(
                    "TARGET_RULE_SOURCE_STATE_CONFLICT",
                    "A rule source clause is absent from persisted policy state.",
                ) from None
            if actual_links != expected_links:
                raise PolicyRuntimePreparationError(
                    "TARGET_RULE_SOURCE_STATE_CONFLICT",
                    "A persisted rule-to-clause source link differs from the bundle.",
                )


def _require_existing_target(
    factory: sessionmaker[Session], *, require_active_user: bool
) -> TenantModel:
    with factory() as session:
        tenant = session.scalar(select(TenantModel).where(TenantModel.slug == TARGET_TENANT))
        if tenant is None:
            raise PolicyRuntimePreparationError(
                "TARGET_TENANT_MISSING", "The existing csight tenant is required."
            )
        if not tenant.is_active:
            raise PolicyRuntimePreparationError(
                "TARGET_TENANT_INACTIVE", "The existing csight tenant is inactive."
            )
        active_users = session.scalar(
            select(func.count(UserModel.id)).where(
                UserModel.tenant_id == tenant.id, UserModel.is_active.is_(True)
            )
        )
        if require_active_user and not active_users:
            raise PolicyRuntimePreparationError(
                "TARGET_ACTIVE_USER_MISSING",
                "An existing active csight user is required for rule activation.",
            )
        session.expunge(tenant)
        return tenant


def preflight_target_database(
    factory: sessionmaker[Session], *, tenant: TenantModel, bundle: PolicyBundle
) -> None:
    """Reject any target state that the preparation path would need to replace or retire."""

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
    expected_rule_sets = _rule_sets_from_bundle(bundle)
    faulty_rule_set = _faulty_rule_set_from_bundle(bundle)
    expected_history = (*expected_rule_sets, faulty_rule_set)
    expected_rule_sets_by_version = {item.rule_set_version: item for item in expected_history}
    expected_v2_index_id = uuid5(
        NAMESPACE_URL,
        f"urn:csight:policy-index:{tenant.id}:{INDEX_NAME}:{INDEX_VERSION}",
    )
    expected_legacy_index_id = uuid5(
        NAMESPACE_URL,
        f"urn:csight:policy-index:{tenant.id}:{INDEX_NAME}:{LEGACY_INDEX_VERSION}",
    )
    v2_index_metadata = CorpusIndexMetadata(
        name=CORPUS_NAME,
        version=CORPUS_VERSION,
        source_hash=bundle.corpus_source_hash,
        document_count=bundle.document_count,
        clause_count=bundle.clause_count,
    )
    legacy_documents = tuple(
        item for item in documents if not item.document_id.startswith("CSC-OPS-")
    )
    legacy_index_metadata = CorpusIndexMetadata(
        name=CORPUS_NAME,
        version=LEGACY_CORPUS_VERSION,
        source_hash=sha256_text("".join(item.source_hash for item in legacy_documents)),
        document_count=EXPECTED_LEGACY_DOCUMENT_COUNT,
        clause_count=EXPECTED_LEGACY_CLAUSE_COUNT,
    )
    with factory() as session:
        existing_documents = tuple(
            session.scalars(
                select(PolicyDocumentModel).where(PolicyDocumentModel.tenant_id == tenant.id)
            )
        )
        existing_clauses = tuple(
            session.scalars(
                select(PolicyClauseModel).where(PolicyClauseModel.tenant_id == tenant.id)
            )
        )
        validate_persisted_policy_semantics(
            documents=documents,
            clauses=clauses,
            persisted_documents=existing_documents,
            persisted_clauses=existing_clauses,
            require_complete=False,
        )
        indexes = tuple(
            session.scalars(
                select(PolicyIndexVersionModel).where(
                    PolicyIndexVersionModel.tenant_id == tenant.id
                )
            )
        )
        indexes_by_id = {item.id: item for item in indexes}
        if len(indexes_by_id) != len(indexes) or any(
            item.id not in {expected_legacy_index_id, expected_v2_index_id} for item in indexes
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_INDEX_STATE_CONFLICT",
                "Existing target policy indexes are outside the immutable v1-to-v2 path.",
            )
        legacy_index = indexes_by_id.get(expected_legacy_index_id)
        v2_index = indexes_by_id.get(expected_v2_index_id)
        existing_legacy_documents = tuple(
            item for item in existing_documents if not item.document_id.startswith("CSC-OPS-")
        )
        existing_legacy_clauses = tuple(
            item for item in existing_clauses if not item.document_id.startswith("CSC-OPS-")
        )
        if legacy_index is not None and (
            len(existing_legacy_documents) != EXPECTED_LEGACY_DOCUMENT_COUNT
            or len(existing_legacy_clauses) != EXPECTED_LEGACY_CLAUSE_COUNT
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_INDEX_STATE_CONFLICT",
                "The preserved legacy index does not have its complete v1 corpus.",
            )
        if v2_index is not None and (
            len(existing_documents) != bundle.document_count
            or len(existing_clauses) != bundle.clause_count
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_INDEX_STATE_CONFLICT",
                "The active v2 index does not have its complete corpus snapshot.",
            )
        try:
            if v2_index is not None:
                _validate_index_state(
                    v2_index,
                    metadata=v2_index_metadata,
                    expected_clause_count=bundle.clause_count,
                    index_version=INDEX_VERSION,
                    expected_status="ACTIVE",
                )
                if legacy_index is not None:
                    _validate_index_state(
                        legacy_index,
                        metadata=legacy_index_metadata,
                        expected_clause_count=EXPECTED_LEGACY_CLAUSE_COUNT,
                        index_version=LEGACY_INDEX_VERSION,
                        expected_status="RETIRED",
                    )
            elif legacy_index is not None:
                _validate_index_state(
                    legacy_index,
                    metadata=legacy_index_metadata,
                    expected_clause_count=EXPECTED_LEGACY_CLAUSE_COUNT,
                    index_version=LEGACY_INDEX_VERSION,
                    expected_status="ACTIVE",
                )
        except ValueError as error:
            raise PolicyRuntimePreparationError(
                "TARGET_INDEX_STATE_CONFLICT", str(error)
            ) from error
        existing_embeddings = tuple(
            session.scalars(
                select(PolicyClauseEmbeddingModel).where(
                    PolicyClauseEmbeddingModel.tenant_id == tenant.id,
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                )
            )
        )
        try:
            clause_records = tuple(to_policy_clause_record(item) for item in existing_clauses)
            embedding_snapshots = tuple(embedding_snapshot(item) for item in existing_embeddings)
            validate_persisted_embedding_integrity(
                clause_records,
                embedding_snapshots,
                require_complete=v2_index is not None,
            )
            if legacy_index is not None and v2_index is None:
                legacy_records = tuple(
                    item for item in clause_records if not item.document_id.startswith("CSC-OPS-")
                )
                legacy_ids = {item.row_id for item in legacy_records}
                legacy_embeddings = tuple(
                    item
                    for item in embedding_snapshots
                    if str(item.policy_clause_row_id) in legacy_ids
                )
                validate_persisted_embedding_integrity(
                    legacy_records,
                    legacy_embeddings,
                    require_complete=True,
                )
        except ValueError as error:
            raise PolicyRuntimePreparationError(
                "TARGET_EMBEDDING_STATE_CONFLICT", str(error)
            ) from error
        rule_set_rows = tuple(
            session.scalars(
                select(PolicyRuleSetModel).where(PolicyRuleSetModel.tenant_id == tenant.id)
            )
        )
        persisted_rule_sets_by_version = {item.rule_set_version: item for item in rule_set_rows}
        persisted_versions = set(persisted_rule_sets_by_version)
        if (
            len(persisted_rule_sets_by_version) != len(rule_set_rows)
            or any(
                item.rule_set_version not in expected_rule_sets_by_version for item in rule_set_rows
            )
            or persisted_versions
            not in (
                set(),
                {LEGACY_RULE_SET_VERSION},
                {LEGACY_RULE_SET_VERSION, RULE_SET_VERSION},
                {LEGACY_RULE_SET_VERSION, FAULTY_RULE_SET_VERSION},
                {
                    LEGACY_RULE_SET_VERSION,
                    FAULTY_RULE_SET_VERSION,
                    RULE_SET_VERSION,
                },
            )
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_RULE_SET_STATE_CONFLICT",
                "Existing target rule sets are outside the immutable v1-to-v2 path.",
            )
        persisted_rules = tuple(
            session.scalars(select(PolicyRuleModel).where(PolicyRuleModel.tenant_id == tenant.id))
        )
        persisted_source_links = tuple(
            session.scalars(
                select(PolicyRuleSourceClauseModel).where(
                    PolicyRuleSourceClauseModel.tenant_id == tenant.id
                )
            )
        )
        validate_persisted_rule_semantics(
            expected_rule_sets=expected_history,
            persisted_rule_sets=rule_set_rows,
            persisted_rules=persisted_rules,
            persisted_source_links=persisted_source_links,
            persisted_clauses=existing_clauses,
            require_complete=False,
        )
        active_activations = tuple(
            session.scalars(
                select(PolicyRuleSetActivationModel).where(
                    PolicyRuleSetActivationModel.tenant_id == tenant.id,
                    PolicyRuleSetActivationModel.retired_at.is_(None),
                )
            )
        )
        expected_active_version = (
            RULE_SET_VERSION
            if RULE_SET_VERSION in persisted_rule_sets_by_version
            else (
                FAULTY_RULE_SET_VERSION
                if FAULTY_RULE_SET_VERSION in persisted_rule_sets_by_version
                else LEGACY_RULE_SET_VERSION
            )
        )
        expected_active_row = persisted_rule_sets_by_version.get(expected_active_version)
        if active_activations and (
            len(active_activations) != 1
            or expected_active_row is None
            or active_activations[0].rule_set_id != expected_active_row.id
        ):
            raise PolicyRuntimePreparationError(
                "TARGET_RULE_ACTIVATION_CONFLICT",
                "Existing target rule activation cannot be retired by this demo path.",
            )
        if rule_set_rows and not active_activations:
            raise PolicyRuntimePreparationError(
                "TARGET_RULE_SET_INACTIVE",
                "An existing derived rule set is inactive and requires explicit operator review.",
            )


def verify_runtime(
    factory: sessionmaker[Session], *, tenant: TenantModel, bundle: PolicyBundle
) -> RuntimePreparationSummary:
    ingested_rule_sets = _rule_sets_from_bundle(bundle)
    ingested_rule_sets_by_version = {item.rule_set_version: item for item in ingested_rule_sets}
    faulty_rule_set = _faulty_rule_set_from_bundle(bundle)
    active_rule_set = ingested_rule_sets_by_version[RULE_SET_VERSION]
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
    v2_index_metadata = CorpusIndexMetadata(
        name=CORPUS_NAME,
        version=CORPUS_VERSION,
        source_hash=bundle.corpus_source_hash,
        document_count=bundle.document_count,
        clause_count=bundle.clause_count,
    )
    legacy_documents = tuple(
        item for item in documents if not item.document_id.startswith("CSC-OPS-")
    )
    legacy_index_metadata = CorpusIndexMetadata(
        name=CORPUS_NAME,
        version=LEGACY_CORPUS_VERSION,
        source_hash=sha256_text("".join(item.source_hash for item in legacy_documents)),
        document_count=EXPECTED_LEGACY_DOCUMENT_COUNT,
        clause_count=EXPECTED_LEGACY_CLAUSE_COUNT,
    )
    expected_v2_index_id = uuid5(
        NAMESPACE_URL,
        f"urn:csight:policy-index:{tenant.id}:{INDEX_NAME}:{INDEX_VERSION}",
    )
    expected_legacy_index_id = uuid5(
        NAMESPACE_URL,
        f"urn:csight:policy-index:{tenant.id}:{INDEX_NAME}:{LEGACY_INDEX_VERSION}",
    )
    with factory() as session:
        persisted_documents = tuple(
            session.scalars(
                select(PolicyDocumentModel).where(PolicyDocumentModel.tenant_id == tenant.id)
            )
        )
        persisted_clauses = tuple(
            session.scalars(
                select(PolicyClauseModel).where(PolicyClauseModel.tenant_id == tenant.id)
            )
        )
        persisted_embeddings = tuple(
            session.scalars(
                select(PolicyClauseEmbeddingModel).where(
                    PolicyClauseEmbeddingModel.tenant_id == tenant.id,
                    PolicyClauseEmbeddingModel.embedding_profile_id == PROFILE_ID,
                )
            )
        )
        indexes = tuple(
            session.scalars(
                select(PolicyIndexVersionModel).where(
                    PolicyIndexVersionModel.tenant_id == tenant.id,
                )
            )
        )
        persisted_rule_sets = tuple(
            session.scalars(
                select(PolicyRuleSetModel).where(PolicyRuleSetModel.tenant_id == tenant.id)
            )
        )
        persisted_rule_sets_by_version = {
            item.rule_set_version: item for item in persisted_rule_sets
        }
        active_activations = tuple(
            session.scalars(
                select(PolicyRuleSetActivationModel).where(
                    PolicyRuleSetActivationModel.tenant_id == tenant.id,
                    PolicyRuleSetActivationModel.retired_at.is_(None),
                )
            )
        )
        persisted_rules = tuple(
            session.scalars(select(PolicyRuleModel).where(PolicyRuleModel.tenant_id == tenant.id))
        )
        persisted_source_links = tuple(
            session.scalars(
                select(PolicyRuleSourceClauseModel).where(
                    PolicyRuleSourceClauseModel.tenant_id == tenant.id
                )
            )
        )
        try:
            validate_persisted_policy_semantics(
                documents=documents,
                clauses=clauses,
                persisted_documents=persisted_documents,
                persisted_clauses=persisted_clauses,
                require_complete=True,
            )
            validate_persisted_embedding_integrity(
                tuple(to_policy_clause_record(row) for row in persisted_clauses),
                tuple(embedding_snapshot(row) for row in persisted_embeddings),
                require_complete=True,
            )
            indexes_by_id = {item.id: item for item in indexes}
            if len(indexes_by_id) != len(indexes) or any(
                item.id not in {expected_legacy_index_id, expected_v2_index_id} for item in indexes
            ):
                raise ValueError("target contains an unexpected policy index")
            v2_index = indexes_by_id.get(expected_v2_index_id)
            if v2_index is None:
                raise ValueError("target v2 policy index is missing")
            _validate_index_state(
                v2_index,
                metadata=v2_index_metadata,
                expected_clause_count=bundle.clause_count,
                index_version=INDEX_VERSION,
                expected_status="ACTIVE",
            )
            legacy_index = indexes_by_id.get(expected_legacy_index_id)
            if legacy_index is not None:
                _validate_index_state(
                    legacy_index,
                    metadata=legacy_index_metadata,
                    expected_clause_count=EXPECTED_LEGACY_CLAUSE_COUNT,
                    index_version=LEGACY_INDEX_VERSION,
                    expected_status="RETIRED",
                )
        except (PolicyRuntimePreparationError, ValueError) as error:
            raise PolicyRuntimePreparationError(
                "RUNTIME_VERIFICATION_FAILED", str(error)
            ) from error
        persisted_versions = set(persisted_rule_sets_by_version)
        allowed_complete_versions = (
            {LEGACY_RULE_SET_VERSION, RULE_SET_VERSION},
            {
                LEGACY_RULE_SET_VERSION,
                FAULTY_RULE_SET_VERSION,
                RULE_SET_VERSION,
            },
        )
        if persisted_versions not in allowed_complete_versions:
            raise PolicyRuntimePreparationError(
                "RUNTIME_VERIFICATION_FAILED",
                "The immutable v1/2.0.0/2.0.1 rule-set history is invalid.",
            )
        expected_rule_sets = (
            (*ingested_rule_sets, faulty_rule_set)
            if FAULTY_RULE_SET_VERSION in persisted_versions
            else ingested_rule_sets
        )
        expected_rule_sets_by_version = {item.rule_set_version: item for item in expected_rule_sets}
        validate_persisted_rule_semantics(
            expected_rule_sets=expected_rule_sets,
            persisted_rule_sets=persisted_rule_sets,
            persisted_rules=persisted_rules,
            persisted_source_links=persisted_source_links,
            persisted_clauses=persisted_clauses,
            require_complete=True,
        )
        for version, expected in expected_rule_sets_by_version.items():
            row = persisted_rule_sets_by_version[version]
            if (
                row.rule_set_name != expected.rule_set_name
                or row.effective_from != expected.effective_from
                or row.effective_to != expected.effective_to
                or row.source_corpus_name != expected.source_corpus_name
                or row.source_corpus_version != expected.source_corpus_version
                or row.source_corpus_hash != expected.source_corpus_hash
                or row.content_hash != expected.content_hash
            ):
                raise PolicyRuntimePreparationError(
                    "RUNTIME_VERIFICATION_FAILED",
                    "A persisted rule set differs from its immutable bundle version.",
                )
        active_row = persisted_rule_sets_by_version[RULE_SET_VERSION]
        if (
            len(active_activations) != 1
            or active_activations[0].rule_set_id != active_row.id
            or active_row.content_hash != active_rule_set.content_hash
        ):
            raise PolicyRuntimePreparationError(
                "RUNTIME_VERIFICATION_FAILED", "Policy rule set v2 is not the sole ACTIVE version."
            )
        persisted_clauses_by_id = {item.clause_id: item for item in persisted_clauses}
        rules_by_set_and_identity = {
            (item.rule_set_id, item.rule_id, item.rule_version): item for item in persisted_rules
        }
        links_by_rule_id: dict[object, list[PolicyRuleSourceClauseModel]] = {}
        for link in persisted_source_links:
            links_by_rule_id.setdefault(link.policy_rule_id, []).append(link)
        for version, expected_set in expected_rule_sets_by_version.items():
            rule_set_row = persisted_rule_sets_by_version[version]
            for expected_rule in expected_set.rules:
                row = rules_by_set_and_identity.get(
                    (rule_set_row.id, expected_rule.rule_id, expected_rule.rule_version)
                )
                if row is None or (
                    row.category != expected_rule.category.value
                    or row.priority != expected_rule.priority
                    or row.conditions
                    != [item.model_dump(mode="json") for item in expected_rule.conditions]
                    or row.effects
                    != [item.model_dump(mode="json") for item in expected_rule.effects]
                    or row.requires_human_review != expected_rule.requires_human_review
                    or row.prohibit_final_decision != expected_rule.prohibit_final_decision
                    or row.content_hash != expected_rule.content_hash
                ):
                    raise PolicyRuntimePreparationError(
                        "RUNTIME_VERIFICATION_FAILED",
                        "A persisted typed rule differs from its immutable source.",
                    )
                actual_links = links_by_rule_id.get(row.id, [])
                actual_link_state = {
                    (
                        item.clause_id,
                        item.document_id,
                        item.document_version,
                        item.source_hash,
                        item.policy_clause_row_id,
                    )
                    for item in actual_links
                }
                expected_link_state = {
                    (
                        item.clause_id,
                        item.document_id,
                        item.document_version,
                        item.source_hash,
                        persisted_clauses_by_id[item.clause_id].id,
                    )
                    for item in expected_rule.source_references
                }
                if actual_link_state != expected_link_state:
                    raise PolicyRuntimePreparationError(
                        "RUNTIME_VERIFICATION_FAILED",
                        "A persisted rule-to-clause source link differs from the bundle.",
                    )
        expected_rule_count = sum(len(item.rules) for item in expected_rule_sets)
        expected_source_link_count = sum(
            len(rule.source_references) for item in expected_rule_sets for rule in item.rules
        )
    document_count = len(persisted_documents)
    clause_count = len(persisted_clauses)
    embedding_count = len(persisted_embeddings)
    active_index_count = sum(item.status == "ACTIVE" for item in indexes)
    rule_count = len(persisted_rules)
    source_link_count = len(persisted_source_links)
    if (
        document_count != bundle.document_count
        or clause_count != bundle.clause_count
        or embedding_count != bundle.clause_count
        or active_index_count != 1
        or rule_count != expected_rule_count
        or source_link_count != expected_source_link_count
    ):
        raise PolicyRuntimePreparationError(
            "RUNTIME_VERIFICATION_FAILED", "The csight synthetic policy runtime is incomplete."
        )
    return RuntimePreparationSummary(
        ingestion_reused=False,
        embedding_reused=0,
        embedding_created=0,
        rule_sets_inserted=0,
        rules_inserted=0,
        document_count=document_count,
        clause_count=clause_count,
        embedding_count=embedding_count,
        active_index_count=active_index_count,
        active_rule_set_count=len(active_activations),
        rule_count=rule_count,
        source_link_count=source_link_count,
    )


def prepare_runtime(
    *,
    settings: Settings,
    source_corpus_root: Path,
    source_rules_path: Path,
    operations_v2_root: Path = DEFAULT_V2_POLICY_ROOT,
    output_root: Path,
    embedding_base_url: str,
    batch_size: int,
) -> tuple[PolicyBundle, RuntimePreparationSummary]:
    embedding_base_url = require_local_runtime(
        environment=settings.environment,
        database_url=settings.database_url_value,
        embedding_base_url=embedding_base_url,
    )
    factory = create_session_factory(get_engine(settings))
    tenant = _require_existing_target(factory, require_active_user=True)
    bundle = materialize_policy_bundle(
        source_corpus_root=source_corpus_root,
        source_rules_path=source_rules_path,
        operations_v2_root=operations_v2_root,
        output_root=output_root,
    )
    preflight_target_database(factory, tenant=tenant, bundle=bundle)
    with session_scope(factory) as session:
        ingestion = ingest_validated_policy_corpus(
            session=session,
            corpus_root=bundle.corpus_root,
            allow_synthetic_tenant_creation=False,
        )
    embedding = build_policy_embeddings(
        settings=settings,
        embedding_base_url=embedding_base_url,
        batch_size=batch_size,
        tenant_slug=TARGET_TENANT,
        corpus_manifest=bundle.corpus_manifest,
        protect_existing_index=False,
        index_name=INDEX_NAME,
        index_version=INDEX_VERSION,
    )
    rule_sets = _rule_sets_from_bundle(bundle)
    inserted_sets, inserted_rules = SQLAlchemyPolicyEngineRepository(factory).ingest(rule_sets)
    verified = verify_runtime(factory, tenant=tenant, bundle=bundle)
    return bundle, RuntimePreparationSummary(
        ingestion_reused=ingestion.reused,
        embedding_reused=embedding.reused,
        embedding_created=embedding.created,
        rule_sets_inserted=inserted_sets,
        rules_inserted=inserted_rules,
        document_count=verified.document_count,
        clause_count=verified.clause_count,
        embedding_count=verified.embedding_count,
        active_index_count=verified.active_index_count,
        active_rule_set_count=verified.active_rule_set_count,
        rule_count=verified.rule_count,
        source_link_count=verified.source_link_count,
    )


def _local_data_output(repository_root: Path, value: Path) -> Path:
    output = value if value.is_absolute() else repository_root / value
    resolved = output.resolve()
    local_data = (repository_root / "local-data").resolve()
    if not resolved.is_relative_to(local_data) or resolved == local_data:
        raise PolicyRuntimePreparationError(
            "OUTPUT_OUTSIDE_LOCAL_DATA", "Derived policy artifacts must stay under local-data/."
        )
    return resolved


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("local-data/csight-synthetic-policy-runtime-v2.0.1"),
    )
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--batch-size", type=int, default=16)
    arguments = parser.parse_args()
    try:
        output_root = _local_data_output(repository_root, arguments.output_root)
        settings = Settings(_env_file=arguments.env_file)  # pyright: ignore[reportCallIssue]
        bundle, summary = prepare_runtime(
            settings=settings,
            source_corpus_root=repository_root / "data" / "policy_corpus",
            source_rules_path=(
                repository_root
                / "data"
                / "policy_rules"
                / "normalized"
                / "policy_rule_sets_v1.jsonl"
            ),
            operations_v2_root=repository_root / "data" / "csight_commerce_policy_v2",
            output_root=output_root,
            embedding_base_url=arguments.embedding_base_url,
            batch_size=arguments.batch_size,
        )
    except Exception as error:
        code = getattr(error, "code", type(error).__name__)
        print(f"CSIGHT_SYNTHETIC_POLICY_PREPARATION_FAILED code={code} message={error}")
        return 1
    print(
        "CSIGHT_SYNTHETIC_POLICY_RUNTIME_READY "
        f"bundle_reused={str(bundle.reused).lower()} "
        f"ingestion_reused={str(summary.ingestion_reused).lower()} "
        f"documents={summary.document_count} clauses={summary.clause_count} "
        f"embeddings={summary.embedding_count} embedding_reused={summary.embedding_reused} "
        f"embedding_created={summary.embedding_created} "
        f"active_indexes={summary.active_index_count} "
        f"rule_sets_inserted={summary.rule_sets_inserted} "
        f"rules_inserted={summary.rules_inserted} "
        f"rules={summary.rule_count} source_links={summary.source_link_count} "
        f"active_rule_sets={summary.active_rule_set_count} "
        "scope=SYNTHETIC_REFERENCE_FICTIONAL_DEMO_ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
