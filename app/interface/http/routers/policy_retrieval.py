"""Authenticated read-only policy clause retrieval endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.interface.http.dependencies import (
    provide_current_principal,
    provide_sprint4b_services,
)
from app.interface.http.policy_retrieval_schemas import (
    PolicySearchRequest,
    PolicySearchResponse,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint4BServiceContainer
from app.platform.policy_retrieval import PolicySearchQuery
from app.platform.tenant import Principal

router = APIRouter(prefix="/api/v1/policy-retrieval", tags=["policy-retrieval"])


@router.post(
    "/search",
    response_model=PolicySearchResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def search_policy_clauses(
    body: PolicySearchRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4BServiceContainer, Depends(provide_sprint4b_services)],
) -> PolicySearchResponse:
    result = services.search_policy_clauses.execute(
        principal=principal,
        query=PolicySearchQuery(
            tenant_id=principal.tenant_id,
            query=body.query,
            as_of_date=body.as_of_date,
            mode=body.mode,
            top_k=body.top_k,
            filters=body.filters.to_domain(),
        ),
    )
    return PolicySearchResponse.from_result(result)


__all__ = ["router"]
