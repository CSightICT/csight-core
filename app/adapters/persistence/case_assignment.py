"""PostgreSQL adapter for intake-level Case ownership and audit history."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    CaseAssignmentActionModel,
    CaseAssignmentModel,
    CaseModel,
    HumanReviewActionModel,
    HumanReviewAssignmentModel,
    HumanReviewDecisionModel,
    HumanReviewTaskModel,
    RoleModel,
    UserModel,
    UserRoleModel,
)
from app.platform.case_assignment import (
    CaseAssignmentActionType,
    CaseAssignmentSnapshot,
    CaseAssignmentTargetNotEligibleError,
    CaseAssignmentTerminalError,
    CaseAssignmentType,
    CaseAssignmentVersionConflictError,
)
from app.platform.errors import CaseNotFoundError
from app.platform.human_review import AssignmentType, ReviewActionType, ReviewTaskStatus
from app.platform.tenant import Role


class SQLAlchemyCaseAssignmentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def get(self, *, tenant_id: str, case_id: str) -> CaseAssignmentSnapshot | None:
        identifiers = _identifiers(tenant_id=tenant_id, case_id=case_id)
        if identifiers is None:
            return None
        tenant_uuid, case_uuid = identifiers
        with self._factory() as session:
            row = session.execute(
                select(CaseModel, CaseAssignmentModel)
                .outerjoin(
                    CaseAssignmentModel,
                    (CaseAssignmentModel.tenant_id == CaseModel.tenant_id)
                    & (CaseAssignmentModel.case_id == CaseModel.id)
                    & CaseAssignmentModel.released_at.is_(None),
                )
                .where(CaseModel.tenant_id == tenant_uuid, CaseModel.id == case_uuid)
            ).one_or_none()
        if row is None:
            return None
        case, assignment = row
        return _snapshot(case=case, assignment=assignment)

    def exists(self, *, tenant_id: str, case_id: str) -> bool:
        identifiers = _identifiers(tenant_id=tenant_id, case_id=case_id)
        if identifiers is None:
            return False
        tenant_uuid, case_uuid = identifiers
        with self._factory() as session:
            return bool(
                session.scalar(
                    select(
                        exists().where(
                            CaseModel.tenant_id == tenant_uuid,
                            CaseModel.id == case_uuid,
                        )
                    )
                )
            )

    def can_access(
        self,
        *,
        tenant_id: str,
        case_id: str,
        actor_id: str,
    ) -> bool:
        identifiers = _identifiers(tenant_id=tenant_id, case_id=case_id)
        try:
            actor_uuid = UUID(actor_id)
        except ValueError:
            return False
        if identifiers is None:
            return False
        tenant_uuid, case_uuid = identifiers
        completed_by_actor = exists(
            select(HumanReviewDecisionModel.id)
            .join(
                HumanReviewTaskModel,
                (HumanReviewTaskModel.tenant_id == HumanReviewDecisionModel.tenant_id)
                & (HumanReviewTaskModel.id == HumanReviewDecisionModel.review_task_id),
            )
            .where(
                HumanReviewDecisionModel.tenant_id == tenant_uuid,
                HumanReviewTaskModel.case_id == case_uuid,
                HumanReviewDecisionModel.decided_by == actor_uuid,
            )
        )
        with self._factory() as session:
            return bool(
                session.scalar(
                    select(
                        exists().where(
                            CaseModel.tenant_id == tenant_uuid,
                            CaseModel.id == case_uuid,
                            or_(
                                CaseModel.current_assignee_id == actor_uuid,
                                completed_by_actor,
                            ),
                        )
                    )
                )
            )

    def assign(
        self,
        *,
        tenant_id: str,
        case_id: str,
        assignee_id: str,
        assigned_by: str,
        expected_version: int,
        rationale: str,
    ) -> CaseAssignmentSnapshot:
        tenant_uuid = UUID(tenant_id)
        case_uuid = UUID(case_id)
        assignee_uuid = UUID(assignee_id)
        actor_uuid = UUID(assigned_by)
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            case = session.scalars(
                select(CaseModel)
                .where(CaseModel.tenant_id == tenant_uuid, CaseModel.id == case_uuid)
                .with_for_update()
            ).one_or_none()
            if case is None:
                raise CaseNotFoundError()
            if case.status == "RESOLVED":
                raise CaseAssignmentTerminalError()
            if case.assignment_version != expected_version:
                raise CaseAssignmentVersionConflictError(
                    details={"current_version": case.assignment_version}
                )
            _require_eligible_assignee(
                session,
                tenant_id=tenant_uuid,
                assignee_id=assignee_uuid,
            )
            active = session.scalars(
                select(CaseAssignmentModel)
                .where(
                    CaseAssignmentModel.tenant_id == tenant_uuid,
                    CaseAssignmentModel.case_id == case_uuid,
                    CaseAssignmentModel.released_at.is_(None),
                )
                .with_for_update()
            ).one_or_none()
            if case.current_assignee_id == assignee_uuid and active is not None:
                return _snapshot(case=case, assignment=active)

            previous_assignee = case.current_assignee_id
            if active is not None:
                active.released_at = now
            resulting_version = expected_version + 1
            assignment_type = (
                CaseAssignmentType.ADMIN_REASSIGNMENT
                if previous_assignee is not None
                else CaseAssignmentType.ADMIN_ASSIGNMENT
            )
            action_type = (
                CaseAssignmentActionType.REASSIGNED
                if previous_assignee is not None
                else CaseAssignmentActionType.ASSIGNED
            )
            assignment = CaseAssignmentModel(
                id=uuid4(),
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                assignee_id=assignee_uuid,
                assigned_by=actor_uuid,
                assignment_type=assignment_type.value,
                rationale=rationale,
                assigned_at=now,
                released_at=None,
                created_at=now,
            )
            session.add(assignment)
            session.add(
                CaseAssignmentActionModel(
                    id=uuid4(),
                    tenant_id=tenant_uuid,
                    case_id=case_uuid,
                    action_type=action_type.value,
                    from_assignee_id=previous_assignee,
                    to_assignee_id=assignee_uuid,
                    actor_id=actor_uuid,
                    rationale=rationale,
                    expected_version=expected_version,
                    resulting_version=resulting_version,
                    occurred_at=now,
                    created_at=now,
                )
            )
            case.current_assignee_id = assignee_uuid
            case.assignment_version = resulting_version
            case.updated_at = now
            _inherit_open_review_tasks(
                session,
                tenant_id=tenant_uuid,
                case_id=case_uuid,
                assignee_id=assignee_uuid,
                actor_id=actor_uuid,
                case_assignment_version=resulting_version,
                rationale=rationale,
                now=now,
            )
            session.flush()
            return _snapshot(case=case, assignment=assignment)


def _identifiers(*, tenant_id: str, case_id: str) -> tuple[UUID, UUID] | None:
    try:
        return UUID(tenant_id), UUID(case_id)
    except ValueError:
        return None


def _require_eligible_assignee(session: Session, *, tenant_id: UUID, assignee_id: UUID) -> None:
    roles = set(
        session.scalars(
            select(RoleModel.name)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .join(
                UserModel,
                (UserModel.tenant_id == UserRoleModel.tenant_id)
                & (UserModel.id == UserRoleModel.user_id),
            )
            .where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == assignee_id,
                UserModel.is_active.is_(True),
                RoleModel.name.in_((Role.ADMIN.value, Role.REVIEWER.value)),
            )
        )
    )
    if not roles:
        raise CaseAssignmentTargetNotEligibleError()


def _inherit_open_review_tasks(
    session: Session,
    *,
    tenant_id: UUID,
    case_id: UUID,
    assignee_id: UUID,
    actor_id: UUID,
    case_assignment_version: int,
    rationale: str,
    now: datetime,
) -> None:
    tasks = session.scalars(
        select(HumanReviewTaskModel)
        .where(
            HumanReviewTaskModel.tenant_id == tenant_id,
            HumanReviewTaskModel.case_id == case_id,
            HumanReviewTaskModel.status != ReviewTaskStatus.RESOLVED.value,
        )
        .order_by(HumanReviewTaskModel.created_at, HumanReviewTaskModel.id)
        .with_for_update()
    ).all()
    for task in tasks:
        previous_assignee = task.current_assignee_id
        active = session.scalars(
            select(HumanReviewAssignmentModel)
            .where(
                HumanReviewAssignmentModel.tenant_id == tenant_id,
                HumanReviewAssignmentModel.review_task_id == task.id,
                HumanReviewAssignmentModel.released_at.is_(None),
            )
            .with_for_update()
        ).one_or_none()
        if previous_assignee == assignee_id and active is not None:
            continue
        if active is not None:
            active.released_at = now
        previous_status = task.status
        next_status = (
            ReviewTaskStatus.CLAIMED.value
            if previous_status in {ReviewTaskStatus.PENDING.value, ReviewTaskStatus.ESCALATED.value}
            else previous_status
        )
        expected_task_version = task.version
        resulting_task_version = expected_task_version + 1
        session.add(
            HumanReviewAssignmentModel(
                id=uuid4(),
                tenant_id=tenant_id,
                review_task_id=task.id,
                assignee_id=assignee_id,
                assigned_by=actor_id,
                assignment_type=AssignmentType.CASE_ASSIGNMENT_INHERITANCE.value,
                assigned_at=now,
                released_at=None,
                created_at=now,
            )
        )
        session.add(
            HumanReviewActionModel(
                id=uuid4(),
                tenant_id=tenant_id,
                review_task_id=task.id,
                action_type=(
                    ReviewActionType.REASSIGNED.value
                    if previous_assignee is not None
                    else ReviewActionType.ASSIGNED.value
                ),
                from_status=previous_status,
                to_status=next_status,
                actor_id=actor_id,
                actor_role=Role.ADMIN.value,
                reason_codes=[],
                rationale=rationale,
                action_payload={
                    "assignment_type": AssignmentType.CASE_ASSIGNMENT_INHERITANCE.value,
                    "case_assignment_version": case_assignment_version,
                    "previous_assignee_id": (
                        str(previous_assignee) if previous_assignee is not None else None
                    ),
                    "assignee_id": str(assignee_id),
                },
                expected_task_version=expected_task_version,
                resulting_task_version=resulting_task_version,
                created_at=now,
            )
        )
        task.current_assignee_id = assignee_id
        task.status = next_status
        task.version = resulting_task_version
        task.updated_at = now


def _snapshot(
    *,
    case: CaseModel,
    assignment: CaseAssignmentModel | None,
) -> CaseAssignmentSnapshot:
    return CaseAssignmentSnapshot(
        case_id=str(case.id),
        current_assignee_id=(
            str(case.current_assignee_id) if case.current_assignee_id is not None else None
        ),
        version=case.assignment_version,
        assigned_by=(str(assignment.assigned_by) if assignment is not None else None),
        assignment_type=(
            CaseAssignmentType(assignment.assignment_type) if assignment is not None else None
        ),
        rationale=(assignment.rationale if assignment is not None else None),
        assigned_at=(assignment.assigned_at if assignment is not None else None),
    )


__all__ = ["SQLAlchemyCaseAssignmentRepository"]
