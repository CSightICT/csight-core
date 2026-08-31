"""Tenant-scoped Case commands and queries."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.case import (
    Case,
    CaseSourceScope,
    CaseStatus,
    CaseStatusTransition,
    IdempotencyRecord,
    JsonValue,
    RequestedAction,
    validate_json_object,
)
from app.platform.errors import (
    CaseNotFoundError,
    IdempotencyKeyReusedError,
    InconsistentPersistenceStateError,
)
from app.platform.signed_intake import AuthenticatedSignedIntake
from app.platform.tenant import Permission, Principal, Role
from app.ports.case_repository import CaseListCriteria
from app.ports.runtime import Clock, IdGenerator
from app.ports.unit_of_work import CaseUnitOfWorkFactory

CREATE_CASE_OPERATION = "case.create.v1"
SIGNED_INTAKE_CREATE_CASE_OPERATION = "case.intake.signed.v1"
IDEMPOTENCY_RETENTION = timedelta(hours=24)


class ApplicationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CreateCaseCommand(ApplicationDTO):
    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=1, max_length=20_000)
    requested_action: RequestedAction = RequestedAction.UNSPECIFIED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("customer_message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("customer_message must not be blank")
        return normalized

    @field_validator("attributes")
    @classmethod
    def require_json_attributes(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return validate_json_object(value)


class CreateCaseResult(ApplicationDTO):
    case: Case
    replayed: bool = False


class CreateSignedIntakeCaseCommand(ApplicationDTO):
    source_event_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    case: CreateCaseCommand


class ListCasesQuery(ApplicationDTO):
    status: CaseStatus | None = None
    order_ref: str | None = Field(default=None, min_length=1, max_length=200)
    product_ref: str | None = Field(default=None, min_length=1, max_length=200)
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("created_from", "created_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("date filters must be timezone-aware")
        return value.astimezone(UTC)

    def criteria(self) -> CaseListCriteria:
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("created_from must not be later than created_to")
        return CaseListCriteria(**self.model_dump())


class CasePage(ApplicationDTO):
    items: tuple[Case, ...]
    page: int
    page_size: int
    total: int


def canonical_case_request_hash(command: CreateCaseCommand) -> str:
    payload = command.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_signed_intake_case_request_hash(
    *,
    authenticated: AuthenticatedSignedIntake,
    command: CreateSignedIntakeCaseCommand,
) -> str:
    payload = {
        "source_id": authenticated.source.source_id,
        "source_event_id": command.source_event_id,
        "case": command.case.model_dump(mode="json", exclude={"idempotency_key"}),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _signed_intake_idempotency_key(*, source_id: str, source_event_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}\0{source_event_id}".encode()).hexdigest()
    return f"signed:{digest}"


def _create_case(
    *,
    uow_factory: CaseUnitOfWorkFactory,
    clock: Clock,
    id_generator: IdGenerator,
    tenant_id: str,
    actor_id: str,
    command: CreateCaseCommand,
    operation: str,
    idempotency_key: str | None,
    request_hash: str | None,
    source_scope: CaseSourceScope | None = None,
    source_provenance: str | None = None,
) -> CreateCaseResult:
    now = clock.now().astimezone(UTC)
    case = Case.create(
        case_id=id_generator.new_id(),
        tenant_id=tenant_id,
        order_ref=command.order_ref,
        product_ref=command.product_ref,
        customer_message=command.customer_message,
        requested_action=command.requested_action,
        attributes=command.attributes,
        created_by=actor_id,
        now=now,
        source_scope=source_scope,
        source_provenance=source_provenance,
    )
    transition = CaseStatusTransition.initial(
        transition_id=id_generator.new_id(), case=case, now=now
    )

    with uow_factory() as uow:
        if idempotency_key is not None:
            if request_hash is None:
                raise ValueError("an idempotent Case creation requires a request hash")
            candidate = IdempotencyRecord(
                id=id_generator.new_id(),
                tenant_id=tenant_id,
                operation=operation,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resource_type="case",
                resource_id=case.id,
                response_status=201,
                created_at=now,
                expires_at=now + IDEMPOTENCY_RETENTION,
            )
            claim = uow.idempotency.claim(tenant_id=tenant_id, record=candidate)
            if not claim.claimed:
                if claim.record.request_hash != request_hash:
                    raise IdempotencyKeyReusedError()
                existing = uow.cases.get(
                    tenant_id=tenant_id,
                    case_id=claim.record.resource_id,
                )
                if existing is None:
                    raise InconsistentPersistenceStateError()
                return CreateCaseResult(case=existing, replayed=True)

        uow.cases.add(tenant_id=tenant_id, case=case)
        uow.status_history.add(tenant_id=tenant_id, transition=transition)
        uow.flush()
        uow.commit()
    return CreateCaseResult(case=case)


class CreateCase:
    def __init__(
        self,
        *,
        uow_factory: CaseUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, *, principal: Principal, command: CreateCaseCommand) -> CreateCaseResult:
        principal.require(Permission.CASE_CREATE)
        return _create_case(
            uow_factory=self._uow_factory,
            clock=self._clock,
            id_generator=self._id_generator,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            command=command,
            operation=CREATE_CASE_OPERATION,
            idempotency_key=command.idempotency_key,
            request_hash=(
                canonical_case_request_hash(command)
                if command.idempotency_key is not None
                else None
            ),
        )


class CreateSignedIntakeCase:
    def __init__(
        self,
        *,
        uow_factory: CaseUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        authenticated: AuthenticatedSignedIntake,
        command: CreateSignedIntakeCaseCommand,
    ) -> CreateCaseResult:
        source = authenticated.source
        return _create_case(
            uow_factory=self._uow_factory,
            clock=self._clock,
            id_generator=self._id_generator,
            tenant_id=source.tenant_id,
            actor_id=source.actor_user_id,
            command=command.case,
            operation=SIGNED_INTAKE_CREATE_CASE_OPERATION,
            idempotency_key=_signed_intake_idempotency_key(
                source_id=source.source_id,
                source_event_id=command.source_event_id,
            ),
            request_hash=canonical_signed_intake_case_request_hash(
                authenticated=authenticated,
                command=command,
            ),
            source_scope=CaseSourceScope.PILOT_LIVE,
            source_provenance=source.provenance,
        )


class ListCases:
    def __init__(self, *, uow_factory: CaseUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, principal: Principal, query: ListCasesQuery) -> CasePage:
        principal.require(Permission.CASE_READ)
        criteria = query.criteria()
        if not principal.roles & {Role.ADMIN, Role.QUALITY_VIEWER}:
            criteria = replace(criteria, access_actor_id=principal.user_id)
        with self._uow_factory() as uow:
            items = uow.cases.list(tenant_id=principal.tenant_id, criteria=criteria)
            total = uow.cases.count(tenant_id=principal.tenant_id, criteria=criteria)
        return CasePage(items=items, page=query.page, page_size=query.page_size, total=total)


class GetCase:
    def __init__(self, *, uow_factory: CaseUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, principal: Principal, case_id: str) -> Case:
        principal.require(Permission.CASE_READ)
        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
        if case is None:
            raise CaseNotFoundError()
        return case


class GetCaseStatusHistory:
    def __init__(self, *, uow_factory: CaseUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, principal: Principal, case_id: str) -> tuple[CaseStatusTransition, ...]:
        principal.require(Permission.CASE_READ)
        with self._uow_factory() as uow:
            case = uow.cases.get(tenant_id=principal.tenant_id, case_id=case_id)
            if case is None:
                raise CaseNotFoundError()
            return uow.status_history.list(tenant_id=principal.tenant_id, case_id=case_id)
