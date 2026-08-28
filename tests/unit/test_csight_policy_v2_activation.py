"""Transaction-contract tests for immutable csight policy rule-set activation."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.adapters.persistence.models import (
    PolicyClauseModel,
    PolicyRuleModel,
    PolicyRuleSetActivationModel,
    PolicyRuleSetModel,
    PolicyRuleSourceClauseModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.policy_engine import (
    SQLAlchemyPolicyEngineRepository,
    _reconstruct_rule_set,  # pyright: ignore[reportPrivateUsage]
)
from app.platform.errors import ValidationError
from app.platform.policy_engine import PolicyRuleSet
from scripts.prepare_csight_synthetic_policy_runtime import (
    LEGACY_RULE_SET_VERSION,
    RULE_SET_VERSION,
    materialize_policy_bundle,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _FakeState:
    tenant: SimpleNamespace
    user: SimpleNamespace
    clauses: dict[str, SimpleNamespace]
    rule_sets: list[Any] = field(default_factory=list)
    rules: list[Any] = field(default_factory=list)
    source_links: list[Any] = field(default_factory=list)
    activations: list[Any] = field(default_factory=list)
    fail_next_activation: bool = False


def _compiled_parameter(statement: Any, prefix: str) -> object | None:
    return next(
        (value for key, value in statement.compile().params.items() if key.startswith(prefix)),
        None,
    )


class _FakeSession:
    def __init__(self, state: _FakeState) -> None:
        self.state = state

    def scalar(self, statement: Any) -> Any:
        entity = statement.column_descriptions[0]["entity"]
        if entity is TenantModel:
            return self.state.tenant
        if entity is PolicyRuleSetModel:
            version = _compiled_parameter(statement, "rule_set_version")
            return next(
                (item for item in self.state.rule_sets if item.rule_set_version == version),
                None,
            )
        if entity is PolicyClauseModel:
            clause_id = _compiled_parameter(statement, "clause_id")
            return self.state.clauses.get(str(clause_id))
        if entity is UserModel:
            return self.state.user
        raise AssertionError(f"unexpected scalar entity: {entity}")

    def add(self, value: Any) -> None:
        if isinstance(value, PolicyRuleSetModel):
            self.state.rule_sets.append(value)
        elif isinstance(value, PolicyRuleModel):
            self.state.rules.append(value)
        elif isinstance(value, PolicyRuleSourceClauseModel):
            self.state.source_links.append(value)
        elif isinstance(value, PolicyRuleSetActivationModel):
            if self.state.fail_next_activation:
                self.state.fail_next_activation = False
                raise RuntimeError("injected activation failure")
            self.state.activations.append(value)
        else:
            raise AssertionError(f"unexpected persisted value: {type(value)}")

    def flush(self) -> None:
        return None

    def execute(self, statement: Any) -> SimpleNamespace:
        assert statement.table.name == "policy_rule_set_activations"
        retired_at = _compiled_parameter(statement, "retired_at")
        rule_set_name = _compiled_parameter(statement, "rule_set_name")
        affected = 0
        for activation in self.state.activations:
            if activation.rule_set_name == rule_set_name and activation.retired_at is None:
                activation.retired_at = retired_at
                affected += 1
        return SimpleNamespace(rowcount=affected)


class _FakeFactory:
    def __init__(self, state: _FakeState) -> None:
        self.state = state

    @contextmanager
    def begin(self) -> Generator[_FakeSession, None, None]:
        collections = (
            self.state.rule_sets,
            self.state.rules,
            self.state.source_links,
            self.state.activations,
        )
        lengths = tuple(len(items) for items in collections)
        retired_state = tuple(
            (activation, activation.retired_at) for activation in self.state.activations
        )
        try:
            yield _FakeSession(self.state)
        except Exception:
            for items, length in zip(collections, lengths, strict=True):
                del items[length:]
            for activation, retired_at in retired_state:
                activation.retired_at = retired_at
            raise


def _rule_sets(tmp_path: Path) -> tuple[PolicyRuleSet, PolicyRuleSet]:
    bundle = materialize_policy_bundle(
        source_corpus_root=ROOT / "data" / "policy_corpus",
        source_rules_path=ROOT / "data" / "policy_rules/normalized/policy_rule_sets_v1.jsonl",
        operations_v2_root=ROOT / "data" / "csight_commerce_policy_v2",
        output_root=tmp_path / "bundle",
    )
    values = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in bundle.rules_path.read_text(encoding="utf-8").splitlines()
        if line
    )
    legacy = next(item for item in values if item.rule_set_version == LEGACY_RULE_SET_VERSION)
    v2 = next(item for item in values if item.rule_set_version == RULE_SET_VERSION)
    return legacy, v2


def test_v2_activation_is_idempotent_and_failed_successor_rolls_back(tmp_path: Path) -> None:
    legacy, v2 = _rule_sets(tmp_path)
    tenant_id, user_id = uuid4(), uuid4()
    legacy_row_id = uuid4()
    state = _FakeState(
        tenant=SimpleNamespace(id=tenant_id, slug="csight"),
        user=SimpleNamespace(id=user_id, tenant_id=tenant_id, is_active=True),
        clauses={
            source.clause_id: SimpleNamespace(id=uuid4(), clause_id=source.clause_id)
            for rule in v2.rules
            for source in rule.source_references
        },
        rule_sets=[
            SimpleNamespace(
                id=legacy_row_id,
                tenant_id=tenant_id,
                rule_set_name=legacy.rule_set_name,
                rule_set_version=legacy.rule_set_version,
                content_hash=legacy.content_hash,
            )
        ],
        activations=[
            SimpleNamespace(
                id=uuid4(),
                tenant_id=tenant_id,
                rule_set_id=legacy_row_id,
                rule_set_name=legacy.rule_set_name,
                activated_at=object(),
                retired_at=None,
            )
        ],
    )
    repository = SQLAlchemyPolicyEngineRepository(_FakeFactory(state))  # type: ignore[arg-type]

    assert repository.ingest((legacy, v2)) == (1, len(v2.rules))
    v2_row = next(item for item in state.rule_sets if item.rule_set_version == RULE_SET_VERSION)
    assert state.activations[0].retired_at is not None
    assert len(state.activations) == 2
    assert state.activations[1].rule_set_id == v2_row.id
    assert state.activations[1].retired_at is None

    counts = tuple(
        len(items)
        for items in (state.rule_sets, state.rules, state.source_links, state.activations)
    )
    assert repository.ingest((legacy, v2)) == (0, 0)
    assert (
        tuple(
            len(items)
            for items in (state.rule_sets, state.rules, state.source_links, state.activations)
        )
        == counts
    )

    state.fail_next_activation = True
    failed_successor = v2.model_copy(update={"rule_set_version": "3.0.0"})
    with pytest.raises(RuntimeError, match="injected activation failure"):
        repository.ingest((failed_successor,))

    assert not any(item.rule_set_version == "3.0.0" for item in state.rule_sets)
    assert len(state.activations) == 2
    assert state.activations[1].rule_set_id == v2_row.id
    assert state.activations[1].retired_at is None
    assert (
        tuple(
            len(items)
            for items in (state.rule_sets, state.rules, state.source_links, state.activations)
        )
        == counts
    )


def test_v2_persistence_reconstruction_uses_the_same_canonical_hash(tmp_path: Path) -> None:
    _legacy, v2 = _rule_sets(tmp_path)
    tenant_id = uuid4()
    rule_set_row = PolicyRuleSetModel(
        id=uuid4(),
        tenant_id=tenant_id,
        rule_set_name=v2.rule_set_name,
        rule_set_version=v2.rule_set_version,
        effective_from=v2.effective_from,
        effective_to=v2.effective_to,
        source_corpus_name=v2.source_corpus_name,
        source_corpus_version=v2.source_corpus_version,
        source_corpus_hash=v2.source_corpus_hash,
        source_type=v2.source_type,
        rule_schema_version=v2.rule_schema_version,
        field_registry_version=v2.field_registry_version,
        operator_registry_version=v2.operator_registry_version,
        aggregation_version=v2.aggregation_version,
        content_hash=v2.content_hash,
    )
    rule_rows: list[PolicyRuleModel] = []
    source_rows: list[PolicyRuleSourceClauseModel] = []
    for rule in reversed(v2.rules):
        rule_row = PolicyRuleModel(
            id=uuid4(),
            tenant_id=tenant_id,
            rule_set_id=rule_set_row.id,
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            category=rule.category.value,
            priority=rule.priority,
            conditions=[item.model_dump(mode="json") for item in rule.conditions],
            effects=[item.model_dump(mode="json") for item in rule.effects],
            requires_human_review=rule.requires_human_review,
            prohibit_final_decision=rule.prohibit_final_decision,
            content_hash=rule.content_hash,
        )
        rule_rows.append(rule_row)
        for source in reversed(rule.source_references):
            source_rows.append(
                PolicyRuleSourceClauseModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    policy_rule_id=rule_row.id,
                    policy_clause_row_id=uuid4(),
                    document_id=source.document_id,
                    document_version=source.document_version,
                    clause_id=source.clause_id,
                    source_hash=source.source_hash,
                )
            )

    reconstructed = _reconstruct_rule_set(
        tenant_slug="csight",
        row=rule_set_row,
        rule_rows=tuple(rule_rows),
        source_rows=tuple(source_rows),
    )

    assert reconstructed == v2
    assert reconstructed.content_hash == rule_set_row.content_hash


def test_ingest_rejects_noncanonical_multi_source_order_before_transaction(
    tmp_path: Path,
) -> None:
    _legacy, v2 = _rule_sets(tmp_path)
    target = next(item for item in v2.rules if len(item.source_references) > 1)
    noncanonical = target.model_copy(
        update={"source_references": tuple(reversed(target.source_references))}
    )
    rule_set = v2.model_copy(
        update={
            "rules": tuple(
                noncanonical if item.rule_id == target.rule_id else item for item in v2.rules
            )
        }
    )
    state = _FakeState(
        tenant=SimpleNamespace(id=uuid4(), slug="csight"),
        user=SimpleNamespace(id=uuid4(), is_active=True),
        clauses={},
    )

    with pytest.raises(ValidationError, match="canonical order"):
        SQLAlchemyPolicyEngineRepository(_FakeFactory(state)).ingest(  # type: ignore[arg-type]
            (rule_set,)
        )
    assert not state.rule_sets
