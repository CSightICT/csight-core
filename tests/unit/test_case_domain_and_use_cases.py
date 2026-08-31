"""Sprint 1 Case domain, permissions, and idempotency behavior."""

from datetime import UTC, datetime
from types import TracebackType

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.application.cases import (
    CreateCase,
    CreateCaseCommand,
    CreateSignedIntakeCase,
    CreateSignedIntakeCaseCommand,
    GetCase,
    ListCases,
    ListCasesQuery,
    canonical_case_request_hash,
)
from app.platform.case import (
    Case,
    CaseSourceScope,
    CaseStatus,
    CaseStatusTransition,
    IdempotencyRecord,
    JsonValue,
    RequestedAction,
)
from app.platform.errors import CaseNotFoundError, ForbiddenError, IdempotencyKeyReusedError
from app.platform.evidence import EvidenceMetadata, EvidenceUploadStatus, build_evidence_object_key
from app.platform.signed_intake import AuthenticatedSignedIntake, SignedIntakeSource
from app.platform.tenant import Principal, Role
from app.ports.case_repository import (
    CaseListCriteria,
    CaseRepository,
    CaseStatusHistoryRepository,
    EvidenceClaim,
    EvidenceRepository,
    IdempotencyClaim,
    IdempotencyRepository,
)
from app.ports.unit_of_work import CaseUnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)


class StaticClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self) -> None:
        self._value = 0

    def new_id(self) -> str:
        self._value += 1
        return f"00000000-0000-4000-8000-{self._value:012d}"


class FakeCaseRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], Case] = {}

    def add(self, *, tenant_id: str, case: Case) -> None:
        if tenant_id != case.tenant_id:
            raise ValueError("case tenant mismatch")
        self.items[(case.tenant_id, case.id)] = case

    def get(self, *, tenant_id: str, case_id: str) -> Case | None:
        return self.items.get((tenant_id, case_id))

    def list(self, *, tenant_id: str, criteria: CaseListCriteria) -> tuple[Case, ...]:
        items = [case for (scope, _), case in self.items.items() if scope == tenant_id]
        if criteria.status is not None:
            items = [case for case in items if case.status is criteria.status]
        return tuple(sorted(items, key=lambda case: (case.created_at, case.id), reverse=True))

    def count(self, *, tenant_id: str, criteria: CaseListCriteria) -> int:
        return len(self.list(tenant_id=tenant_id, criteria=criteria))


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.items: list[CaseStatusTransition] = []

    def add(self, *, tenant_id: str, transition: CaseStatusTransition) -> None:
        if tenant_id != transition.tenant_id:
            raise ValueError("history tenant mismatch")
        self.items.append(transition)

    def list(self, *, tenant_id: str, case_id: str) -> tuple[CaseStatusTransition, ...]:
        return tuple(
            item for item in self.items if item.tenant_id == tenant_id and item.case_id == case_id
        )


class FakeEvidenceRepository:
    def add(self, *, tenant_id: str, evidence: EvidenceMetadata) -> None:
        if tenant_id != evidence.tenant_id:
            raise ValueError("evidence tenant mismatch")

    def claim(self, *, tenant_id: str, evidence: EvidenceMetadata) -> EvidenceClaim:
        self.add(tenant_id=tenant_id, evidence=evidence)
        return EvidenceClaim(claimed=True, evidence=evidence)

    def get(self, *, tenant_id: str, case_id: str, evidence_id: str) -> EvidenceMetadata | None:
        del tenant_id, case_id, evidence_id
        return None

    def list(self, *, tenant_id: str, case_id: str) -> tuple[EvidenceMetadata, ...]:
        del tenant_id, case_id
        return ()

    def set_upload_status(
        self,
        *,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        status: EvidenceUploadStatus,
        updated_at: datetime,
    ) -> EvidenceMetadata | None:
        del tenant_id, case_id, evidence_id, status, updated_at
        return None


class FakeIdempotencyRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], IdempotencyRecord] = {}

    def claim(self, *, tenant_id: str, record: IdempotencyRecord) -> IdempotencyClaim:
        if tenant_id != record.tenant_id:
            raise ValueError("idempotency tenant mismatch")
        key = (record.tenant_id, record.operation, record.idempotency_key)
        existing = self.items.get(key)
        if existing is not None:
            return IdempotencyClaim(claimed=False, record=existing)
        self.items[key] = record
        return IdempotencyClaim(claimed=True, record=record)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.case_repository = FakeCaseRepository()
        self.history_repository = FakeHistoryRepository()
        self.evidence_repository = FakeEvidenceRepository()
        self.idempotency_repository = FakeIdempotencyRepository()
        self.cases: CaseRepository = self.case_repository
        self.status_history: CaseStatusHistoryRepository = self.history_repository
        self.evidence: EvidenceRepository = self.evidence_repository
        self.idempotency: IdempotencyRepository = self.idempotency_repository
        self.commits = 0

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


class FakeUnitOfWorkFactory:
    def __init__(self, unit_of_work: FakeUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def __call__(self) -> CaseUnitOfWork:
        return self.unit_of_work


def principal(*, tenant_id: str = "tenant-a", role: Role = Role.REVIEWER) -> Principal:
    return Principal(
        user_id=f"user-{tenant_id}",
        tenant_id=tenant_id,
        email=f"reviewer@{tenant_id}.example",
        display_name="Reviewer",
        roles=frozenset({role}),
    )


def command(*, message: str = "Damaged package", key: str | None = None) -> CreateCaseCommand:
    return CreateCaseCommand(
        order_ref="ORD-1",
        product_ref="SKU-1",
        customer_message=message,
        requested_action=RequestedAction.EXCHANGE,
        attributes={"nested": {"days": 3}},
        idempotency_key=key,
    )


def service(unit_of_work: FakeUnitOfWork) -> CreateCase:
    return CreateCase(
        uow_factory=FakeUnitOfWorkFactory(unit_of_work),
        clock=StaticClock(),
        id_generator=SequenceIds(),
    )


def test_case_rejects_blank_customer_message_and_non_finite_json() -> None:
    with pytest.raises(PydanticValidationError, match="customer_message"):
        command(message="   ")
    with pytest.raises(PydanticValidationError, match="finite"):
        CreateCaseCommand(
            order_ref="ORD-1",
            product_ref="SKU-1",
            customer_message="Valid",
            attributes={"score": float("nan")},
        )


@pytest.mark.parametrize(
    ("attributes", "message"),
    [
        ({"": "value"}, "must not be blank"),
        ({"x" * 129: "value"}, "128 characters"),
        ({f"key-{index}": index for index in range(257)}, "256 keys"),
        ({"payload": "가" * 30_000}, "65536 UTF-8 bytes"),
    ],
)
def test_case_rejects_unbounded_attributes(
    attributes: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(PydanticValidationError, match=message):
        CreateCaseCommand(
            order_ref="ORD-1",
            product_ref="SKU-1",
            customer_message="Valid",
            attributes=attributes,
        )


def test_case_rejects_attributes_deeper_than_eight_levels() -> None:
    nested: dict[str, JsonValue] = {"leaf": True}
    for index in range(8):
        nested = {f"level-{index}": nested}

    with pytest.raises(PydanticValidationError, match="8 levels"):
        CreateCaseCommand(
            order_ref="ORD-1",
            product_ref="SKU-1",
            customer_message="Valid",
            attributes=nested,
        )


def test_create_case_starts_received_and_records_initial_history() -> None:
    unit_of_work = FakeUnitOfWork()

    result = service(unit_of_work).execute(principal=principal(), command=command())

    assert result.case.status is CaseStatus.RECEIVED
    assert result.case.tenant_id == "tenant-a"
    assert result.replayed is False
    assert len(unit_of_work.case_repository.items) == 1
    assert len(unit_of_work.history_repository.items) == 1
    transition = unit_of_work.history_repository.items[0]
    assert transition.from_status is None
    assert transition.to_status is CaseStatus.RECEIVED
    assert transition.reason == "case_created"
    assert unit_of_work.commits == 1


def test_quality_viewer_cannot_create_but_can_read_cases() -> None:
    unit_of_work = FakeUnitOfWork()
    viewer = principal(role=Role.QUALITY_VIEWER)
    with pytest.raises(ForbiddenError):
        service(unit_of_work).execute(principal=viewer, command=command())

    assert (
        ListCases(uow_factory=FakeUnitOfWorkFactory(unit_of_work))
        .execute(principal=viewer, query=ListCasesQuery())
        .total
        == 0
    )


def test_case_lookup_is_tenant_scoped() -> None:
    unit_of_work = FakeUnitOfWork()
    created = service(unit_of_work).execute(principal=principal(), command=command()).case

    assert (
        GetCase(uow_factory=FakeUnitOfWorkFactory(unit_of_work)).execute(
            principal=principal(), case_id=created.id
        )
        == created
    )
    with pytest.raises(CaseNotFoundError, match="requested case was not found"):
        GetCase(uow_factory=FakeUnitOfWorkFactory(unit_of_work)).execute(
            principal=principal(tenant_id="tenant-b"), case_id=created.id
        )


def test_idempotency_replays_same_body_and_rejects_different_body() -> None:
    unit_of_work = FakeUnitOfWork()
    create_case = service(unit_of_work)

    first = create_case.execute(principal=principal(), command=command(key="same-key"))
    replay = create_case.execute(principal=principal(), command=command(key="same-key"))

    assert replay.replayed is True
    assert replay.case.id == first.case.id
    assert len(unit_of_work.case_repository.items) == 1
    with pytest.raises(IdempotencyKeyReusedError):
        create_case.execute(
            principal=principal(),
            command=command(key="same-key", message="Different payload"),
        )


def test_request_hash_is_stable_and_excludes_idempotency_key() -> None:
    first = canonical_case_request_hash(command(key="first"))
    second = canonical_case_request_hash(command(key="second"))

    assert first == second
    assert len(first) == 64


def test_object_key_never_uses_the_original_filename() -> None:
    key = build_evidence_object_key(
        tenant_id="tenant-a", case_id="case-a", evidence_id="evidence-a"
    )

    assert key == "tenants/tenant-a/cases/case-a/evidence/evidence-a/original"
    assert "filename" not in key


def test_signed_intake_creates_only_pilot_live_and_replays_one_source_event() -> None:
    unit_of_work = FakeUnitOfWork()
    create_case = CreateSignedIntakeCase(
        uow_factory=FakeUnitOfWorkFactory(unit_of_work),
        clock=StaticClock(),
        id_generator=SequenceIds(),
    )
    authenticated = AuthenticatedSignedIntake(
        source=SignedIntakeSource(
            key_id="crm-key-1",
            source_id="customer-crm",
            tenant_id="tenant-a",
            actor_user_id="service-actor-a",
            provenance="signed/crm/v1",
        ),
        authenticated_at=NOW,
    )
    intake = CreateSignedIntakeCaseCommand(source_event_id="event-1", case=command())

    first = create_case.execute(authenticated=authenticated, command=intake)
    replay = create_case.execute(authenticated=authenticated, command=intake)

    assert first.case.source_scope is CaseSourceScope.PILOT_LIVE
    assert first.case.source_provenance == "signed/crm/v1"
    assert first.case.created_by == "service-actor-a"
    assert first.case.status is CaseStatus.RECEIVED
    assert replay.replayed is True
    assert replay.case.id == first.case.id
    assert len(unit_of_work.case_repository.items) == 1
    assert len(unit_of_work.history_repository.items) == 1
    assert unit_of_work.commits == 1

    changed = CreateSignedIntakeCaseCommand(
        source_event_id="event-1",
        case=command(message="Changed payload"),
    )
    with pytest.raises(IdempotencyKeyReusedError):
        create_case.execute(authenticated=authenticated, command=changed)
