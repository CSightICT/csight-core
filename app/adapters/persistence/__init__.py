"""SQLAlchemy persistence adapter primitives."""

from app.adapters.persistence.base import NAMING_CONVENTION, Base
from app.adapters.persistence.engine import (
    DatabaseConfigurationError,
    clear_engine_cache,
    get_engine,
)
from app.adapters.persistence.identity import (
    SQLAlchemyIdentityRepository,
    SQLAlchemyIdentityRepositoryFactoryAdapter,
)
from app.adapters.persistence.models import (
    PERSISTENCE_MODELS,
    CaseEvidenceModel,
    CaseModel,
    CaseStatusHistoryModel,
    IdempotencyRecordModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.persistence.repositories import (
    SQLAlchemyCaseRepository,
    SQLAlchemyCaseStatusHistoryRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyIdempotencyRepository,
)
from app.adapters.persistence.session import create_session_factory, session_scope
from app.adapters.persistence.unit_of_work import (
    SQLAlchemyCaseUnitOfWork,
    SQLAlchemyCaseUnitOfWorkFactory,
    create_case_unit_of_work_factory,
)

__all__ = [
    "NAMING_CONVENTION",
    "PERSISTENCE_MODELS",
    "Base",
    "CaseEvidenceModel",
    "CaseModel",
    "CaseStatusHistoryModel",
    "DatabaseConfigurationError",
    "IdempotencyRecordModel",
    "RoleModel",
    "SQLAlchemyCaseRepository",
    "SQLAlchemyCaseStatusHistoryRepository",
    "SQLAlchemyCaseUnitOfWork",
    "SQLAlchemyCaseUnitOfWorkFactory",
    "SQLAlchemyEvidenceRepository",
    "SQLAlchemyIdempotencyRepository",
    "SQLAlchemyIdentityRepository",
    "SQLAlchemyIdentityRepositoryFactoryAdapter",
    "TenantModel",
    "UserModel",
    "UserRoleModel",
    "clear_engine_cache",
    "create_case_unit_of_work_factory",
    "create_session_factory",
    "get_engine",
    "session_scope",
]
