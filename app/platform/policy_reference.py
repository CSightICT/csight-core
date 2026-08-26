"""Technology-neutral synthetic policy corpus contracts and deterministic builder."""

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SYNTHETIC_DISCLAIMER = (
    "이 Corpus는 CSight PoC의 검색·평가를 위해 제작한 합성 정책 Reference이며, "
    "실제 기업 정책이나 법률 자문을 의미하지 않는다."
)
POLICY_TYPES = frozenset(
    {
        "RETURN_EXCHANGE",
        "SHIPPING_DAMAGE",
        "LEAKAGE_CONTAMINATION",
        "MISSING_COMPONENT",
        "EVIDENCE_REQUIREMENT",
        "HIGH_RISK_EXCEPTION",
        "WRONG_ITEM",
        "FUNCTIONAL_FAILURE",
        "PACKAGING_DAMAGE",
    }
)
DEFECT_TYPES = frozenset(
    {
        "BREAKAGE",
        "PACKAGING_DAMAGE",
        "LEAKAGE",
        "MISSING_COMPONENT",
        "CONTAMINATION",
        "WRONG_ITEM",
        "FUNCTIONAL_FAILURE",
    }
)


class ClauseType(StrEnum):
    RULE = "RULE"
    EXCEPTION = "EXCEPTION"
    EVIDENCE_REQUIREMENT = "EVIDENCE_REQUIREMENT"
    ESCALATION = "ESCALATION"
    DEFINITION = "DEFINITION"
    PROCEDURE = "PROCEDURE"


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PolicyDocument(_StrictModel):
    tenant_id: str
    document_id: str
    document_version: str
    title: str
    policy_type: str
    authority_level: str
    product_categories: tuple[str, ...]
    effective_from: date
    effective_to: date | None = None
    status: DocumentStatus
    source_type: str
    supersedes: str | None = None
    superseded_by: str | None = None
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str

    @model_validator(mode="after")
    def validate_policy_document(self) -> Self:
        if self.policy_type not in POLICY_TYPES:
            raise ValueError("unsupported policy_type")
        if self.source_type != "SYNTHETIC_REFERENCE":
            raise ValueError("every Sprint 4A policy document must be synthetic")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if self.status is DocumentStatus.RETIRED and not self.superseded_by:
            raise ValueError("retired document requires superseded_by")
        return self

    @property
    def version_key(self) -> str:
        return f"{self.document_id}@{self.document_version}"


class PolicyClause(_StrictModel):
    tenant_id: str
    document_id: str
    document_version: str
    clause_id: str
    section_path: tuple[str, ...]
    clause_type: ClauseType
    text: str = Field(min_length=1)
    parent_clause_id: str | None = None
    policy_type: str
    product_categories: tuple[str, ...]
    defect_types: tuple[str, ...]
    actions: tuple[str, ...]
    requires_human_review: bool
    effective_from: date
    effective_to: date | None
    document_status: DocumentStatus
    source_type: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy_clause(self) -> Self:
        if self.policy_type not in POLICY_TYPES:
            raise ValueError("unsupported policy_type")
        if any(item not in DEFECT_TYPES for item in self.defect_types):
            raise ValueError("unsupported defect_type")
        if self.source_type != "SYNTHETIC_REFERENCE":
            raise ValueError("every Sprint 4A policy clause must be synthetic")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return " ".join(value.split())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_document(path: Path, *, root: Path) -> tuple[PolicyDocument, tuple[PolicyClause, ...]]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"missing front matter: {path}")
    try:
        front, body = raw[4:].split("\n---\n", maxsplit=1)
    except ValueError as error:
        raise ValueError(f"unterminated front matter: {path}") from error
    metadata = _parse_front_matter(front)
    source_hash = sha256_text(unicodedata.normalize("NFC", raw))
    document = PolicyDocument(
        tenant_id=metadata["tenant_id"],
        document_id=metadata["document_id"],
        document_version=metadata["document_version"],
        title=metadata["title"],
        policy_type=metadata["policy_type"],
        authority_level=metadata["authority_level"],
        product_categories=_csv(metadata["product_categories"]),
        effective_from=date.fromisoformat(metadata["effective_from"]),
        effective_to=(
            date.fromisoformat(metadata["effective_to"]) if metadata["effective_to"] else None
        ),
        status=DocumentStatus(metadata["status"]),
        source_type=metadata["source_type"],
        supersedes=metadata["supersedes"] or None,
        superseded_by=metadata["superseded_by"] or None,
        source_hash=source_hash,
        source_path=str(path.relative_to(root)),
    )
    clauses = _parse_clauses(body, document=document)
    return document, clauses


def _parse_front_matter(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in value.splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            raise ValueError(f"invalid front matter line: {line}")
        result[key.strip()] = raw_value.strip()
    required = {
        "tenant_id",
        "document_id",
        "document_version",
        "title",
        "policy_type",
        "authority_level",
        "product_categories",
        "effective_from",
        "effective_to",
        "status",
        "source_type",
        "supersedes",
        "superseded_by",
    }
    if set(result) != required:
        raise ValueError(f"front matter keys differ: missing={required - set(result)}")
    return result


_CLAUSE_PATTERN = re.compile(
    r"^##\s+(?P<number>C\d+)\s+\[(?P<type>[A-Z_]+)\]\n\n"
    r"(?P<text>.+?)\n\nTags:\s*(?P<tags>[^\n]+)$",
    re.MULTILINE | re.DOTALL,
)


def _parse_clauses(body: str, *, document: PolicyDocument) -> tuple[PolicyClause, ...]:
    heading = next(
        (line[2:].strip() for line in body.splitlines() if line.startswith("# ")),
        document.title,
    )
    matches = tuple(_CLAUSE_PATTERN.finditer(body))
    if not matches:
        raise ValueError(f"document has no clauses: {document.version_key}")
    clauses: list[PolicyClause] = []
    id_by_number: dict[str, str] = {}
    for match in matches:
        number = match.group("number")
        clause_id = f"{document.document_id}:{document.document_version}:{number}"
        id_by_number[number] = clause_id
        tags = _parse_tags(match.group("tags"))
        defect_types = _csv(tags.get("defects", ""))
        if any(item not in DEFECT_TYPES for item in defect_types):
            raise ValueError(f"unsupported defect type in {clause_id}")
        parent_number = tags.get("parent") or None
        parent_id = id_by_number.get(parent_number) if parent_number else None
        if parent_number and parent_id is None:
            raise ValueError(f"broken parent in {clause_id}")
        clause_type = ClauseType(match.group("type"))
        text_value = normalize_text(match.group("text"))
        clauses.append(
            PolicyClause(
                tenant_id=document.tenant_id,
                document_id=document.document_id,
                document_version=document.document_version,
                clause_id=clause_id,
                section_path=(heading, number),
                clause_type=clause_type,
                text=text_value,
                parent_clause_id=parent_id,
                policy_type=document.policy_type,
                product_categories=_csv(tags.get("categories", "")),
                defect_types=defect_types,
                actions=_csv(tags.get("actions", "")),
                requires_human_review=clause_type in {ClauseType.EXCEPTION, ClauseType.ESCALATION},
                effective_from=document.effective_from,
                effective_to=document.effective_to,
                document_status=document.status,
                source_type=document.source_type,
                source_hash=document.source_hash,
                content_hash=sha256_text(text_value),
            )
        )
    return tuple(clauses)


def _parse_tags(value: str) -> dict[str, str]:
    return {
        key.strip(): raw.strip()
        for item in value.split(";")
        for key, separator, raw in [item.partition("=")]
        if separator
    }


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def resolve_version(
    documents: tuple[PolicyDocument, ...], *, tenant_id: str, document_id: str, as_of: date
) -> PolicyDocument | None:
    eligible = [
        document
        for document in documents
        if document.tenant_id == tenant_id
        and document.document_id == document_id
        and document.status is DocumentStatus.ACTIVE
        and document.effective_from <= as_of
        and (document.effective_to is None or as_of <= document.effective_to)
    ]
    return max(eligible, key=lambda item: _semver(item.document_version), default=None)


def _semver(value: str) -> tuple[int, int, int]:
    parts = tuple(int(part) for part in value.split("."))
    if len(parts) != 3:
        raise ValueError(f"invalid semantic version: {value}")
    return parts


def build_corpus(root: Path) -> dict[str, Any]:
    raw_dir = root / "raw"
    documents: list[PolicyDocument] = []
    clauses: list[PolicyClause] = []
    for path in sorted(raw_dir.glob("*/*.md")):
        document, parsed = parse_document(path, root=root)
        documents.append(document)
        clauses.extend(parsed)
    validate_corpus(tuple(documents), tuple(clauses))
    exact = _duplicates(clauses)
    near = _near_duplicates(clauses)
    source_hash = sha256_text("".join(document.source_hash for document in documents))
    manifest: dict[str, Any] = {
        "corpus_name": "csight_synthetic_policy_reference",
        "corpus_version": "1.0.0",
        "created_at": "2026-08-26T00:00:00Z",
        "source_type": "SYNTHETIC_REFERENCE",
        "document_count": len(documents),
        "clause_count": len(clauses),
        "tenant_count": len({item.tenant_id for item in documents}),
        "policy_type_distribution": dict(
            sorted(Counter(item.policy_type for item in documents).items())
        ),
        "clause_type_distribution": dict(
            sorted(Counter(item.clause_type.value for item in clauses).items())
        ),
        "active_version_count": sum(item.status is DocumentStatus.ACTIVE for item in documents),
        "retired_version_count": sum(item.status is DocumentStatus.RETIRED for item in documents),
        "exception_count": sum(item.clause_type is ClauseType.EXCEPTION for item in clauses),
        "evidence_requirement_count": sum(
            item.clause_type is ClauseType.EVIDENCE_REQUIREMENT for item in clauses
        ),
        "exact_duplicate_count": len(exact),
        "near_duplicate_candidate_count": len(near),
        "source_hash": source_hash,
        "builder_version": "1.0.0",
        "schema_version": "1.0",
        "disclaimer": SYNTHETIC_DISCLAIMER,
    }
    _write_jsonl(root / "normalized" / "policy_documents_v1.jsonl", documents)
    _write_jsonl(root / "clauses" / "policy_clauses_v1.jsonl", clauses)
    _write_json(root / "manifests" / "policy_corpus_v1.json", manifest)
    quality = {
        **manifest,
        "duplicate_clause_ids": [],
        "broken_reference_count": 0,
        "empty_clause_count": 0,
        "near_duplicate_candidates": near,
    }
    _write_json(root / "reports" / "policy_corpus_quality_v1.json", quality)
    _write_quality_markdown(root / "reports" / "policy_corpus_quality_v1.md", quality)
    return manifest


def validate_corpus(
    documents: tuple[PolicyDocument, ...], clauses: tuple[PolicyClause, ...]
) -> None:
    document_keys = [
        (item.tenant_id, item.document_id, item.document_version) for item in documents
    ]
    if len(set(document_keys)) != len(document_keys):
        raise ValueError("duplicate tenant/document/version")
    for document in documents:
        if (
            document.status is DocumentStatus.ACTIVE
            and document.effective_to is not None
            and document.effective_to < date.today()
        ):
            raise ValueError("active document effective_to is in the past")
    clause_ids = [item.clause_id for item in clauses]
    if len(set(clause_ids)) != len(clause_ids):
        raise ValueError("duplicate clause_id")
    document_map = {
        (item.tenant_id, item.document_id, item.document_version): item for item in documents
    }
    clause_map = {item.clause_id: item for item in clauses}
    for clause in clauses:
        document = document_map.get((clause.tenant_id, clause.document_id, clause.document_version))
        if document is None:
            raise ValueError("clause references an unknown document version")
        if (
            clause.policy_type != document.policy_type
            or clause.product_categories != document.product_categories
            or clause.effective_from != document.effective_from
            or clause.effective_to != document.effective_to
            or clause.document_status is not document.status
            or clause.source_type != document.source_type
            or clause.source_hash != document.source_hash
        ):
            raise ValueError("clause metadata differs from its document version")
        if clause.parent_clause_id:
            parent = clause_map.get(clause.parent_clause_id)
            if parent is None:
                raise ValueError("broken parent reference")
            if parent.tenant_id != clause.tenant_id:
                raise ValueError("cross-tenant parent reference")
            if (
                parent.document_id != clause.document_id
                or parent.document_version != clause.document_version
            ):
                raise ValueError("cross-document parent reference")
        if clause.clause_type is ClauseType.EXCEPTION:
            if clause.parent_clause_id is None:
                raise ValueError("exception clause requires a parent rule")
            if clause_map[clause.parent_clause_id].clause_type is not ClauseType.RULE:
                raise ValueError("exception clause parent must be a rule")
    _require_acyclic_relations(
        {item.clause_id: item.parent_clause_id for item in clauses},
        relation_name="parent clause",
    )
    versions = {(item.tenant_id, item.version_key): item for item in documents}
    for document in documents:
        if document.supersedes:
            previous = versions.get((document.tenant_id, document.supersedes))
            if previous is None:
                raise ValueError("broken or cross-tenant supersedes relation")
            if previous.status is not DocumentStatus.RETIRED:
                raise ValueError("superseded document must be retired")
            if previous.superseded_by != document.version_key:
                raise ValueError("supersedes relation must be reciprocal")
        if document.superseded_by:
            replacement = versions.get((document.tenant_id, document.superseded_by))
            if replacement is None:
                raise ValueError("broken or cross-tenant superseded_by relation")
            if replacement.supersedes != document.version_key:
                raise ValueError("superseded_by relation must be reciprocal")
    _require_acyclic_relations(
        {
            f"{item.tenant_id}:{item.version_key}": (
                f"{item.tenant_id}:{item.superseded_by}" if item.superseded_by else None
            )
            for item in documents
        },
        relation_name="document supersession",
    )
    if len(documents) < 18 or len(clauses) < 120:
        raise ValueError("minimum corpus size not met")
    if len({item.tenant_id for item in documents}) < 2:
        raise ValueError("minimum tenant coverage not met")
    if len({item.policy_type for item in documents}) < 6:
        raise ValueError("minimum policy type coverage not met")
    if sum(item.clause_type is ClauseType.EXCEPTION for item in clauses) < 12:
        raise ValueError("minimum exception coverage not met")
    if sum(item.clause_type is ClauseType.EVIDENCE_REQUIREMENT for item in clauses) < 12:
        raise ValueError("minimum evidence requirement coverage not met")
    if sum(item.status is DocumentStatus.RETIRED for item in documents) < 6:
        raise ValueError("minimum retired version coverage not met")


def _require_acyclic_relations(relations: dict[str, str | None], *, relation_name: str) -> None:
    for start in relations:
        visited: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in visited:
                raise ValueError(f"cyclic {relation_name} relation")
            visited.add(current)
            current = relations.get(current)


def _duplicates(clauses: list[PolicyClause]) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for clause in clauses:
        groups.setdefault(clause.content_hash, []).append(clause.clause_id)
    return [ids for ids in groups.values() if len(ids) > 1]


def _near_duplicates(clauses: list[PolicyClause]) -> list[list[str]]:
    candidates: list[list[str]] = []
    for index, left in enumerate(clauses):
        left_tokens = set(left.text.split())
        for right in clauses[index + 1 :]:
            if left.tenant_id != right.tenant_id or left.content_hash == right.content_hash:
                continue
            right_tokens = set(right.text.split())
            union = left_tokens | right_tokens
            if union and len(left_tokens & right_tokens) / len(union) >= 0.9:
                candidates.append([left.clause_id, right.clause_id])
    return candidates


def _jsonable(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _write_jsonl(path: Path, values: Sequence[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True) for value in values
    )
    path.write_text(content + "\n", encoding="utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_quality_markdown(path: Path, quality: dict[str, Any]) -> None:
    path.write_text(
        "# Policy Corpus v1 Quality Report\n\n"
        f"> {SYNTHETIC_DISCLAIMER}\n\n"
        f"- Documents: {quality['document_count']}\n"
        f"- Clauses: {quality['clause_count']}\n"
        f"- Tenants: {quality['tenant_count']}\n"
        f"- Retired versions: {quality['retired_version_count']}\n"
        f"- Exceptions: {quality['exception_count']}\n"
        f"- Evidence requirements: {quality['evidence_requirement_count']}\n"
        f"- Exact duplicates: {quality['exact_duplicate_count']}\n"
        f"- Near-duplicate candidates: {quality['near_duplicate_candidate_count']}\n"
        "- Broken references: 0\n- Empty clauses: 0\n",
        encoding="utf-8",
    )
