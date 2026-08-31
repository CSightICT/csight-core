"""Opt-in PostgreSQL integration tests for concrete Case repositories and UoW."""

import base64
import hashlib
import json
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepositoryFactoryAdapter
from app.adapters.persistence.models import (
    CaseEvidenceModel,
    CaseModel,
    CaseSensitivePayloadModel,
    CaseStatusHistoryModel,
    DataLifecycleEventModel,
    IdempotencyRecordModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.privacy_lifecycle import (
    create_privacy_lifecycle_unit_of_work_factory,
)
from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.unit_of_work import (
    SQLAlchemyCaseUnitOfWorkFactory,
    create_case_unit_of_work_factory,
)
from app.adapters.security.signed_intake_signatures import (
    ConfiguredSignedIntakeSourceRegistry,
    Ed25519SignedIntakeSignatureVerifier,
)
from app.application.cases import (
    CreateCase,
    CreateCaseCommand,
    CreateSignedIntakeCase,
)
from app.application.signed_intake import AuthenticateSignedIntake
from app.bootstrap.settings import Settings
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.main import create_app
from app.platform.case import (
    Case,
    CaseSourceScope,
    CaseStatus,
    CaseStatusTransition,
    IdempotencyRecord,
    RequestedAction,
)
from app.platform.errors import IdempotencyKeyReusedError
from app.platform.evidence import EvidenceMetadata, EvidenceType, EvidenceUploadStatus
from app.platform.privacy_lifecycle import (
    PURGED_CUSTOMER_MESSAGE,
    LifecycleMutationStatus,
)
from app.platform.signed_intake import SignedIntakeProof, SignedIntakeSource
from app.platform.tenant import Principal, Role
from app.ports.case_repository import CaseListCriteria, IdempotencyClaim
from app.ports.runtime import Clock, IdGenerator

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 26, 3, 4, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def repository_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test PostgreSQL repositories")

    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for repository integration tests")

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    alembic_command.upgrade(config, "head")

    engine = get_engine(settings)
    try:
        yield engine
    finally:
        clear_engine_cache()


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    engine: Engine
    factory: SQLAlchemyCaseUnitOfWorkFactory
    tenant_a: str
    tenant_b: str
    user_a: str
    user_b: str


@pytest.fixture
def repository_context(repository_engine: Engine) -> Generator[RepositoryContext, None, None]:
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    user_a = str(uuid4())
    user_b = str(uuid4())
    with Session(repository_engine) as session:
        session.add_all(
            [
                TenantModel(id=UUID(tenant_a), slug=f"tenant-{tenant_a}", name="Tenant A"),
                TenantModel(id=UUID(tenant_b), slug=f"tenant-{tenant_b}", name="Tenant B"),
                UserModel(
                    id=UUID(user_a),
                    tenant_id=UUID(tenant_a),
                    email=f"reviewer-{user_a}@example.test",
                    password_hash="test-password-hash",
                    display_name="Reviewer A",
                ),
                UserModel(
                    id=UUID(user_b),
                    tenant_id=UUID(tenant_b),
                    email=f"reviewer-{user_b}@example.test",
                    password_hash="test-password-hash",
                    display_name="Reviewer B",
                ),
            ]
        )
        session.commit()

    context = RepositoryContext(
        engine=repository_engine,
        factory=create_case_unit_of_work_factory(repository_engine),
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        user_a=user_a,
        user_b=user_b,
    )
    try:
        yield context
    finally:
        tenant_ids = [UUID(tenant_a), UUID(tenant_b)]
        with repository_engine.begin() as connection:
            connection.execute(
                delete(IdempotencyRecordModel).where(
                    IdempotencyRecordModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(CaseStatusHistoryModel).where(
                    CaseStatusHistoryModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(CaseEvidenceModel).where(CaseEvidenceModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(DataLifecycleEventModel).where(
                    DataLifecycleEventModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(CaseSensitivePayloadModel).where(
                    CaseSensitivePayloadModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(delete(CaseModel).where(CaseModel.tenant_id.in_(tenant_ids)))
            connection.execute(delete(UserModel).where(UserModel.tenant_id.in_(tenant_ids)))
            connection.execute(delete(TenantModel).where(TenantModel.id.in_(tenant_ids)))


def _case(
    *,
    case_id: str,
    tenant_id: str,
    user_id: str,
    created_at: datetime,
    status: CaseStatus = CaseStatus.RECEIVED,
    order_ref: str = "ORD-1",
    product_ref: str = "SKU-1",
) -> Case:
    return Case(
        id=case_id,
        tenant_id=tenant_id,
        status=status,
        order_ref=order_ref,
        product_ref=product_ref,
        customer_message=f"Message for {case_id}",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"source": "integration"},
        created_by=user_id,
        created_at=created_at,
        updated_at=created_at,
    )


def _evidence(
    *,
    evidence_id: str,
    context: RepositoryContext,
    case_id: str,
    created_at: datetime,
    sha256_character: str,
) -> EvidenceMetadata:
    return EvidenceMetadata(
        id=evidence_id,
        tenant_id=context.tenant_a,
        case_id=case_id,
        evidence_type=EvidenceType.IMAGE,
        upload_status=EvidenceUploadStatus.PENDING,
        storage_bucket="csight-evidence",
        object_key=(f"tenants/{context.tenant_a}/cases/{case_id}/evidence/{evidence_id}/original"),
        original_filename=f"{evidence_id}.png",
        content_type="image/png",
        size_bytes=2048,
        sha256=sha256_character * 64,
        width=800,
        height=600,
        created_by=context.user_a,
        created_at=created_at,
        updated_at=created_at,
    )


def test_case_repository_enforces_tenant_filters_ordering_and_pagination(
    repository_context: RepositoryContext,
) -> None:
    case_one = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
        order_ref="ORD-FILTER",
    )
    case_two = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW + timedelta(minutes=1),
        product_ref="SKU-FILTER",
    )
    case_three = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW + timedelta(minutes=1),
        status=CaseStatus.RESOLVED,
    )
    other_tenant_case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_b,
        user_id=repository_context.user_b,
        created_at=NOW + timedelta(hours=1),
    )
    with repository_context.factory() as unit_of_work:
        for case in (case_one, case_two, case_three, other_tenant_case):
            unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()

    criteria = CaseListCriteria(page=1, page_size=10)
    with repository_context.factory() as unit_of_work:
        actual = unit_of_work.cases.list(
            tenant_id=repository_context.tenant_a,
            criteria=criteria,
        )
        expected = tuple(
            sorted(
                (case_one, case_two, case_three),
                key=lambda case: (case.created_at, case.id),
                reverse=True,
            )
        )
        assert actual == expected
        assert (
            unit_of_work.cases.get(
                tenant_id=repository_context.tenant_b,
                case_id=case_one.id,
            )
            is None
        )
        assert (
            unit_of_work.cases.get(
                tenant_id=repository_context.tenant_a,
                case_id="not-a-uuid",
            )
            is None
        )
        assert unit_of_work.cases.list(
            tenant_id=repository_context.tenant_a,
            criteria=CaseListCriteria(status=CaseStatus.RESOLVED),
        ) == (case_three,)
        assert unit_of_work.cases.list(
            tenant_id=repository_context.tenant_a,
            criteria=CaseListCriteria(order_ref="ORD-FILTER"),
        ) == (case_one,)
        assert unit_of_work.cases.list(
            tenant_id=repository_context.tenant_a,
            criteria=CaseListCriteria(product_ref="SKU-FILTER"),
        ) == (case_two,)
        paged = unit_of_work.cases.list(
            tenant_id=repository_context.tenant_a,
            criteria=CaseListCriteria(page=2, page_size=1),
        )
        assert paged == (expected[1],)
        assert (
            unit_of_work.cases.count(
                tenant_id=repository_context.tenant_a,
                criteria=CaseListCriteria(page=2, page_size=1),
            )
            == 3
        )
        assert (
            unit_of_work.cases.count(
                tenant_id=repository_context.tenant_a,
                criteria=CaseListCriteria(
                    created_from=NOW + timedelta(seconds=1),
                    created_to=NOW + timedelta(minutes=1),
                ),
            )
            == 2
        )


def test_history_and_evidence_repositories_support_case_detail_and_status_updates(
    repository_context: RepositoryContext,
) -> None:
    case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    first_history = CaseStatusTransition.initial(
        transition_id=str(uuid4()),
        case=case,
        now=NOW,
    )
    second_history = CaseStatusTransition(
        id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        case_id=case.id,
        from_status=CaseStatus.RECEIVED,
        to_status=CaseStatus.VALIDATING,
        actor_id=repository_context.user_a,
        reason="validation_started",
        occurred_at=NOW + timedelta(seconds=1),
    )
    first_evidence = _evidence(
        evidence_id=str(uuid4()),
        context=repository_context,
        case_id=case.id,
        created_at=NOW,
        sha256_character="a",
    )
    second_evidence = _evidence(
        evidence_id=str(uuid4()),
        context=repository_context,
        case_id=case.id,
        created_at=NOW + timedelta(seconds=1),
        sha256_character="b",
    )
    with repository_context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()

    with repository_context.factory() as unit_of_work:
        unit_of_work.status_history.add(
            tenant_id=second_history.tenant_id,
            transition=second_history,
        )
        unit_of_work.status_history.add(
            tenant_id=first_history.tenant_id,
            transition=first_history,
        )
        unit_of_work.evidence.add(
            tenant_id=second_evidence.tenant_id,
            evidence=second_evidence,
        )
        unit_of_work.evidence.add(
            tenant_id=first_evidence.tenant_id,
            evidence=first_evidence,
        )
        unit_of_work.commit()

    with repository_context.factory() as unit_of_work:
        assert unit_of_work.status_history.list(
            tenant_id=repository_context.tenant_a,
            case_id=case.id,
        ) == (first_history, second_history)
        assert (
            unit_of_work.status_history.list(
                tenant_id=repository_context.tenant_b,
                case_id=case.id,
            )
            == ()
        )
        assert unit_of_work.evidence.list(
            tenant_id=repository_context.tenant_a,
            case_id=case.id,
        ) == (first_evidence, second_evidence)
        assert (
            unit_of_work.evidence.get(
                tenant_id=repository_context.tenant_b,
                case_id=case.id,
                evidence_id=first_evidence.id,
            )
            is None
        )
        assert (
            unit_of_work.evidence.set_upload_status(
                tenant_id=repository_context.tenant_b,
                case_id=case.id,
                evidence_id=first_evidence.id,
                status=EvidenceUploadStatus.AVAILABLE,
                updated_at=NOW + timedelta(seconds=2),
            )
            is None
        )
        available = unit_of_work.evidence.set_upload_status(
            tenant_id=repository_context.tenant_a,
            case_id=case.id,
            evidence_id=first_evidence.id,
            status=EvidenceUploadStatus.AVAILABLE,
            updated_at=NOW + timedelta(seconds=2),
        )
        unit_of_work.commit()

    assert available is not None
    assert available.upload_status is EvidenceUploadStatus.AVAILABLE
    with repository_context.factory() as unit_of_work:
        failed = unit_of_work.evidence.set_upload_status(
            tenant_id=repository_context.tenant_a,
            case_id=case.id,
            evidence_id=first_evidence.id,
            status=EvidenceUploadStatus.FAILED,
            updated_at=NOW + timedelta(seconds=3),
        )
        unit_of_work.commit()

    assert failed is not None
    assert failed.upload_status is EvidenceUploadStatus.FAILED


class StaticClock(Clock):
    def now(self) -> datetime:
        return NOW


class UUIDGenerator(IdGenerator):
    def new_id(self) -> str:
        return str(uuid4())


def _principal(*, tenant_id: str, user_id: str) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"reviewer-{user_id}@example.test",
        display_name="Reviewer",
        roles=frozenset({Role.REVIEWER}),
    )


def _create_command(
    *, message: str = "Damaged package", key: str = "same-key"
) -> CreateCaseCommand:
    return CreateCaseCommand(
        order_ref="ORD-IDEMPOTENT",
        product_ref="SKU-IDEMPOTENT",
        customer_message=message,
        requested_action=RequestedAction.EXCHANGE,
        idempotency_key=key,
    )


def test_real_create_case_replays_scoped_idempotency_and_rolls_back_mismatch(
    repository_context: RepositoryContext,
) -> None:
    service = CreateCase(
        uow_factory=repository_context.factory,
        clock=StaticClock(),
        id_generator=UUIDGenerator(),
    )
    tenant_a_principal = _principal(
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
    )

    first = service.execute(principal=tenant_a_principal, command=_create_command())
    replay = service.execute(principal=tenant_a_principal, command=_create_command())

    assert replay.replayed is True
    assert replay.case == first.case
    with Session(repository_context.engine) as session:
        payload = session.scalars(
            select(CaseSensitivePayloadModel).where(
                CaseSensitivePayloadModel.tenant_id == UUID(repository_context.tenant_a),
                CaseSensitivePayloadModel.case_id == UUID(first.case.id),
            )
        ).one()
        lifecycle = session.scalars(
            select(DataLifecycleEventModel).where(
                DataLifecycleEventModel.tenant_id == UUID(repository_context.tenant_a),
                DataLifecycleEventModel.case_id == UUID(first.case.id),
            )
        ).one()
    assert payload.customer_message == first.case.customer_message
    assert (
        payload.payload_sha256
        == hashlib.sha256(first.case.customer_message.encode("utf-8")).hexdigest()
    )
    assert payload.retention_policy_version == "development/30d"
    assert lifecycle.event_type == "SENSITIVE_PAYLOAD_CREATED"
    assert lifecycle.details["pii_included"] is False
    with pytest.raises(IdempotencyKeyReusedError):
        service.execute(
            principal=tenant_a_principal,
            command=_create_command(message="A different request"),
        )

    tenant_b_result = service.execute(
        principal=_principal(
            tenant_id=repository_context.tenant_b,
            user_id=repository_context.user_b,
        ),
        command=_create_command(),
    )
    assert tenant_b_result.replayed is False
    assert tenant_b_result.case.tenant_id == repository_context.tenant_b
    with repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.cases.count(
                tenant_id=repository_context.tenant_a,
                criteria=CaseListCriteria(),
            )
            == 1
        )
        assert (
            unit_of_work.cases.count(
                tenant_id=repository_context.tenant_b,
                criteria=CaseListCriteria(),
            )
            == 1
        )


def test_real_signed_intake_replay_writes_one_complete_case_bundle(
    repository_context: RepositoryContext,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    source = SignedIntakeSource(
        key_id="integration-key-1",
        source_id="integration-crm",
        tenant_id=repository_context.tenant_a,
        actor_user_id=repository_context.user_a,
        provenance="signed/integration/v1",
    )
    service = CreateSignedIntakeCase(
        uow_factory=repository_context.factory,
        clock=StaticClock(),
        id_generator=UUIDGenerator(),
    )
    services = SignedIntakeServiceContainer(
        authenticate=AuthenticateSignedIntake(
            sources=ConfiguredSignedIntakeSourceRegistry({source.key_id: source}),
            signatures=Ed25519SignedIntakeSignatureVerifier(
                {source.key_id: private_key.public_key()}
            ),
            identities=SQLAlchemyIdentityRepositoryFactoryAdapter(
                create_session_factory(repository_context.engine)
            ),
            clock=StaticClock(),
        ),
        create_case=service,
        max_body_bytes=128 * 1024,
    )
    client = TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            signed_intake_services=services,
        )
    )

    def payload(message: str) -> bytes:
        return json.dumps(
            {
                "schema_version": "signed_case_intake/1.0.0",
                "order_ref": "ORD-SIGNED-INTEGRATION",
                "product_ref": "SKU-SIGNED-INTEGRATION",
                "customer_message": message,
                "requested_action": "EXCHANGE",
                "attributes": {},
            },
            separators=(",", ":"),
        ).encode()

    def headers(body: bytes) -> dict[str, str]:
        unsigned = SignedIntakeProof(
            method="POST",
            path="/api/v1/integrations/cases",
            key_id=source.key_id,
            event_id="integration-event-1",
            timestamp=int(NOW.timestamp()),
            body_sha256=hashlib.sha256(body).hexdigest(),
            signature_base64=base64.b64encode(bytes(64)).decode(),
        )
        signature = base64.b64encode(private_key.sign(unsigned.canonical_bytes())).decode()
        return {
            "Content-Type": "application/json",
            "X-CSight-Intake-Key-Id": unsigned.key_id,
            "X-CSight-Intake-Event-Id": unsigned.event_id,
            "X-CSight-Intake-Timestamp": str(unsigned.timestamp),
            "X-CSight-Intake-Signature": signature,
        }

    body = payload("Signed integration customer message")
    first = client.post(
        "/api/v1/integrations/cases",
        content=body,
        headers=headers(body),
    )
    replay = client.post(
        "/api/v1/integrations/cases",
        content=body,
        headers=headers(body),
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["case_id"] == first.json()["case_id"]
    assert first.json()["source_scope"] == CaseSourceScope.PILOT_LIVE.value
    case_id = UUID(first.json()["case_id"])
    with Session(repository_context.engine) as session:
        case_count = session.scalar(
            select(func.count()).select_from(CaseModel).where(CaseModel.id == case_id)
        )
        history_count = session.scalar(
            select(func.count())
            .select_from(CaseStatusHistoryModel)
            .where(CaseStatusHistoryModel.case_id == case_id)
        )
        payload_count = session.scalar(
            select(func.count())
            .select_from(CaseSensitivePayloadModel)
            .where(CaseSensitivePayloadModel.case_id == case_id)
        )
        idempotency_count = session.scalar(
            select(func.count())
            .select_from(IdempotencyRecordModel)
            .where(
                IdempotencyRecordModel.tenant_id == UUID(repository_context.tenant_a),
                IdempotencyRecordModel.operation == "case.intake.signed.v1",
            )
        )
    assert (case_count, history_count, payload_count, idempotency_count) == (1, 1, 1, 1)

    conflicting_body = payload("Conflicting signed integration message")
    conflict = client.post(
        "/api/v1/integrations/cases",
        content=conflicting_body,
        headers=headers(conflicting_body),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    with Session(repository_context.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseModel)
                .where(CaseModel.tenant_id == UUID(repository_context.tenant_a))
            )
            == 1
        )


def test_uow_rolls_back_uncommitted_rows_on_normal_and_exception_exit(
    repository_context: RepositoryContext,
) -> None:
    normal_exit_case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    with repository_context.factory() as unit_of_work:
        unit_of_work.cases.add(
            tenant_id=normal_exit_case.tenant_id,
            case=normal_exit_case,
        )
        unit_of_work.flush()

    with repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.cases.get(
                tenant_id=repository_context.tenant_a,
                case_id=normal_exit_case.id,
            )
            is None
        )

    exception_case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    with (
        pytest.raises(RuntimeError, match="force rollback"),
        repository_context.factory() as unit_of_work,
    ):
        unit_of_work.cases.add(
            tenant_id=exception_case.tenant_id,
            case=exception_case,
        )
        unit_of_work.flush()
        raise RuntimeError("force rollback")

    with repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.cases.get(
                tenant_id=repository_context.tenant_a,
                case_id=exception_case.id,
            )
            is None
        )


def test_deferred_idempotency_resource_fk_is_enforced_at_commit(
    repository_context: RepositoryContext,
) -> None:
    case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    record = IdempotencyRecord(
        id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        operation="case.create.v1",
        idempotency_key="deferred-fk-key",
        request_hash="e" * 64,
        resource_type="case",
        resource_id=case.id,
        response_status=201,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )

    with pytest.raises(IntegrityError), repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.idempotency.claim(
                tenant_id=record.tenant_id,
                record=record,
            ).claimed
            is True
        )
        unit_of_work.commit()

    with repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.idempotency.claim(
                tenant_id=record.tenant_id,
                record=record,
            ).claimed
            is True
        )
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()


def _concurrent_claim(
    *,
    factory: SQLAlchemyCaseUnitOfWorkFactory,
    barrier: Barrier,
    record: IdempotencyRecord,
    case: Case,
) -> IdempotencyClaim:
    with factory() as unit_of_work:
        barrier.wait(timeout=10)
        claim = unit_of_work.idempotency.claim(
            tenant_id=record.tenant_id,
            record=record,
        )
        if claim.claimed:
            unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()
        return claim


def test_postgresql_on_conflict_claim_has_one_winner_under_concurrency(
    repository_context: RepositoryContext,
) -> None:
    barrier = Barrier(2)
    candidates: list[tuple[IdempotencyRecord, Case]] = []
    for hash_character in ("c", "d"):
        case = _case(
            case_id=str(uuid4()),
            tenant_id=repository_context.tenant_a,
            user_id=repository_context.user_a,
            created_at=NOW,
        )
        candidates.append(
            (
                IdempotencyRecord(
                    id=str(uuid4()),
                    tenant_id=repository_context.tenant_a,
                    operation="case.create.v1",
                    idempotency_key="concurrent-key",
                    request_hash=hash_character * 64,
                    resource_type="case",
                    resource_id=case.id,
                    response_status=201,
                    created_at=NOW,
                    expires_at=NOW + timedelta(hours=24),
                ),
                case,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _concurrent_claim,
                factory=repository_context.factory,
                barrier=barrier,
                record=record,
                case=case,
            )
            for record, case in candidates
        ]
        claims = [future.result(timeout=15) for future in futures]

    assert sorted(claim.claimed for claim in claims) == [False, True]
    assert len({claim.record.id for claim in claims}) == 1
    assert len({claim.record.resource_id for claim in claims}) == 1
    with repository_context.factory() as unit_of_work:
        assert (
            unit_of_work.cases.count(
                tenant_id=repository_context.tenant_a,
                criteria=CaseListCriteria(),
            )
            == 1
        )


def test_expired_sensitive_payload_purge_is_atomic_idempotent_and_pii_free(
    repository_context: RepositoryContext,
) -> None:
    case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    with repository_context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()

    lifecycle_factory = create_privacy_lifecycle_unit_of_work_factory(repository_context.engine)
    purge_at = NOW + timedelta(days=31)
    with lifecycle_factory() as unit_of_work:
        page = unit_of_work.lifecycle.list_expired_sensitive_payloads(
            tenant_id=repository_context.tenant_a,
            expired_before=purge_at,
            limit=10,
        )
    assert len(page.items) == 1
    candidate = page.items[0]

    with lifecycle_factory() as unit_of_work:
        result = unit_of_work.lifecycle.purge_sensitive_payload(
            candidate=candidate,
            actor_id=repository_context.user_a,
            correlation_id=str(uuid4()),
            occurred_at=purge_at,
        )
        unit_of_work.commit()
    assert result.status is LifecycleMutationStatus.APPLIED

    with Session(repository_context.engine) as session:
        legacy = session.get(CaseModel, UUID(case.id))
        payload = session.scalar(
            select(CaseSensitivePayloadModel).where(
                CaseSensitivePayloadModel.tenant_id == UUID(repository_context.tenant_a),
                CaseSensitivePayloadModel.case_id == UUID(case.id),
            )
        )
        events = session.scalars(
            select(DataLifecycleEventModel).where(
                DataLifecycleEventModel.tenant_id == UUID(repository_context.tenant_a),
                DataLifecycleEventModel.case_id == UUID(case.id),
            )
        ).all()
    assert legacy is not None and legacy.customer_message == PURGED_CUSTOMER_MESSAGE
    assert payload is not None
    assert payload.customer_message is None
    assert payload.purged_at == purge_at
    assert payload.legacy_redacted_at == purge_at
    purge_events = [event for event in events if event.event_type == "SENSITIVE_PAYLOAD_PURGED"]
    assert len(purge_events) == 1
    details = purge_events[0].details
    assert details["outcome"] == "PURGED"
    assert details["pii_included"] is False
    assert details["legacy_copy_redacted"] is True
    assert case.customer_message not in str(details)

    with repository_context.factory() as unit_of_work:
        retained_case = unit_of_work.cases.get(
            tenant_id=repository_context.tenant_a,
            case_id=case.id,
        )
    assert retained_case is not None
    assert retained_case.customer_message == PURGED_CUSTOMER_MESSAGE

    with lifecycle_factory() as unit_of_work:
        replay = unit_of_work.lifecycle.purge_sensitive_payload(
            candidate=candidate,
            actor_id=repository_context.user_a,
            correlation_id=str(uuid4()),
            occurred_at=purge_at,
        )
        unit_of_work.rollback()
    assert replay.status is LifecycleMutationStatus.ALREADY_APPLIED


def test_deferred_sensitive_payload_trigger_rejects_dual_write_drift(
    repository_context: RepositoryContext,
) -> None:
    case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    with repository_context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()

    with Session(repository_context.engine) as session:
        row = session.get(CaseModel, UUID(case.id))
        assert row is not None
        row.customer_message = "drifted compatibility copy"
        with pytest.raises(DBAPIError, match="dual-write mismatch"):
            session.commit()


def test_evidence_status_reconciliation_is_fenced_and_append_only(
    repository_context: RepositoryContext,
) -> None:
    case = _case(
        case_id=str(uuid4()),
        tenant_id=repository_context.tenant_a,
        user_id=repository_context.user_a,
        created_at=NOW,
    )
    evidence = _evidence(
        evidence_id=str(uuid4()),
        context=repository_context,
        case_id=case.id,
        created_at=NOW,
        sha256_character="a",
    )
    with repository_context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.flush()
        unit_of_work.evidence.add(tenant_id=evidence.tenant_id, evidence=evidence)
        unit_of_work.commit()

    lifecycle_factory = create_privacy_lifecycle_unit_of_work_factory(repository_context.engine)
    reconciled_at = NOW + timedelta(hours=2)
    with lifecycle_factory() as unit_of_work:
        page = unit_of_work.lifecycle.list_evidence_for_reconciliation(
            tenant_id=repository_context.tenant_a,
            stale_pending_before=NOW + timedelta(hours=1),
            limit=10,
        )
    record = next(item for item in page.items if item.id == evidence.id)

    with lifecycle_factory() as unit_of_work:
        result = unit_of_work.lifecycle.reconcile_evidence_status(
            record=record,
            target_status=EvidenceUploadStatus.AVAILABLE,
            reason="stale_pending_object_valid",
            actor_id=repository_context.user_a,
            correlation_id=str(uuid4()),
            occurred_at=reconciled_at,
        )
        unit_of_work.commit()
    assert result.status is LifecycleMutationStatus.APPLIED

    with Session(repository_context.engine) as session:
        stored = session.get(CaseEvidenceModel, UUID(evidence.id))
        events = session.scalars(
            select(DataLifecycleEventModel).where(
                DataLifecycleEventModel.tenant_id == UUID(repository_context.tenant_a),
                DataLifecycleEventModel.case_id == UUID(case.id),
                DataLifecycleEventModel.event_type == "EVIDENCE_RECONCILED",
            )
        ).all()
    assert stored is not None and stored.upload_status == EvidenceUploadStatus.AVAILABLE.value
    assert len(events) == 1
    assert events[0].details == {
        "reason": "stale_pending_object_valid",
        "from_status": "PENDING",
        "to_status": "AVAILABLE",
        "pii_included": False,
    }

    with lifecycle_factory() as unit_of_work:
        replay = unit_of_work.lifecycle.reconcile_evidence_status(
            record=record,
            target_status=EvidenceUploadStatus.AVAILABLE,
            reason="stale_pending_object_valid",
            actor_id=repository_context.user_a,
            correlation_id=str(uuid4()),
            occurred_at=reconciled_at,
        )
        unit_of_work.rollback()
    assert replay.status is LifecycleMutationStatus.ALREADY_APPLIED
