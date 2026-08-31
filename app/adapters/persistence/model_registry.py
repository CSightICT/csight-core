"""Complete persistence model registry loaded by Alembic without bloating models.py."""

from app.adapters.persistence.model_activation import (
    LLMModelActivationEventModel,
    LLMReleaseManifestModel,
)
from app.adapters.persistence.model_routing import LLMModelRoutePlanModel
from app.adapters.persistence.models import PERSISTENCE_MODELS as CORE_PERSISTENCE_MODELS
from app.adapters.persistence.oidc_sessions import (
    OidcLoginTransactionModel,
    OidcSessionModel,
)

PERSISTENCE_MODELS = (
    *CORE_PERSISTENCE_MODELS,
    OidcLoginTransactionModel,
    OidcSessionModel,
    LLMReleaseManifestModel,
    LLMModelActivationEventModel,
    LLMModelRoutePlanModel,
)

__all__ = ["PERSISTENCE_MODELS"]
