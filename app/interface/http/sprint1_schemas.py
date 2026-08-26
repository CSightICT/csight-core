"""Public Sprint 1 HTTP contracts.

These models intentionally do not reuse persistence entities.  In particular,
tenant scope is never accepted from a request body, query, or multipart form;
it is resolved from the authenticated principal.
"""

from datetime import datetime
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.application.cases import CasePage, CreateCaseResult
from app.application.evidence import EvidenceAccessUrl
from app.interface.http.analysis_schemas import AnalysisRunResponse
from app.platform.analysis import AnalysisRun
from app.platform.case import (
    Case,
    CaseStatus,
    CaseStatusTransition,
    DomainType,
    JsonValue,
    RequestedAction,
    validate_json_object,
)
from app.platform.evidence import EvidenceMetadata, EvidenceType, EvidenceUploadStatus
from app.platform.tenant import Principal, Role

SPRINT1_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
)


class LoginRequest(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    tenant_slug: str = Field(min_length=1, max_length=63)
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(
        min_length=1,
        max_length=1024,
        json_schema_extra={"format": "password"},
    )

    @field_validator("tenant_slug", "email", mode="before")
    @classmethod
    def normalize_login_identifier(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class TokenResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)


class CurrentUserResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    user_id: str
    tenant_id: str
    email: str
    display_name: str
    roles: tuple[Role, ...]

    @classmethod
    def from_principal(cls, principal: Principal) -> Self:
        return cls(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            email=principal.email,
            display_name=principal.display_name,
            roles=tuple(sorted(principal.roles, key=lambda role: role.value)),
        )


class CreateCaseRequest(BaseModel):
    """Tenant-free Case input; tenant scope always comes from the bearer principal."""

    model_config = SPRINT1_MODEL_CONFIG

    order_ref: str = Field(min_length=1, max_length=200)
    product_ref: str = Field(min_length=1, max_length=200)
    customer_message: str = Field(min_length=1, max_length=20_000, repr=False)
    requested_action: RequestedAction = RequestedAction.UNSPECIFIED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

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


class CreateCaseResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    case_id: str
    status: CaseStatus
    created_at: datetime

    @classmethod
    def from_result(cls, result: CreateCaseResult) -> Self:
        return cls(
            case_id=result.case.id,
            status=result.case.status,
            created_at=result.case.created_at,
        )


class CaseListParameters(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    status: CaseStatus | None = None
    order_ref: str | None = Field(default=None, min_length=1, max_length=200)
    product_ref: str | None = Field(default=None, min_length=1, max_length=200)
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def require_ordered_date_range(self) -> Self:
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("created_from must not be later than created_to")
        return self


class CaseSummaryResponse(BaseModel):
    """List projection deliberately excludes the full customer message."""

    model_config = SPRINT1_MODEL_CONFIG

    case_id: str
    tenant_id: str
    domain_type: DomainType
    status: CaseStatus
    order_ref: str
    product_ref: str
    requested_action: RequestedAction
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_case(cls, case: Case) -> Self:
        return cls(
            case_id=case.id,
            tenant_id=case.tenant_id,
            domain_type=case.domain_type,
            status=case.status,
            order_ref=case.order_ref,
            product_ref=case.product_ref,
            requested_action=case.requested_action,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )


class CaseListResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    items: tuple[CaseSummaryResponse, ...]
    page: int
    page_size: int
    total: int

    @classmethod
    def from_page(cls, page: CasePage) -> Self:
        return cls(
            items=tuple(CaseSummaryResponse.from_case(case) for case in page.items),
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )


class StatusHistoryResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    history_id: str
    from_status: CaseStatus | None
    to_status: CaseStatus
    actor_id: str
    reason: str
    occurred_at: datetime

    @classmethod
    def from_transition(cls, transition: CaseStatusTransition) -> Self:
        return cls(
            history_id=transition.id,
            from_status=transition.from_status,
            to_status=transition.to_status,
            actor_id=transition.actor_id,
            reason=transition.reason,
            occurred_at=transition.occurred_at,
        )


class StatusHistoryListResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    items: tuple[StatusHistoryResponse, ...]


class EvidenceResponse(BaseModel):
    """Safe Evidence metadata projection without storage credentials or signed URLs."""

    model_config = SPRINT1_MODEL_CONFIG

    evidence_id: str
    tenant_id: str
    case_id: str
    evidence_type: EvidenceType
    upload_status: EvidenceUploadStatus
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    width: int
    height: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_evidence(cls, evidence: EvidenceMetadata) -> Self:
        return cls(
            evidence_id=evidence.id,
            tenant_id=evidence.tenant_id,
            case_id=evidence.case_id,
            evidence_type=evidence.evidence_type,
            upload_status=evidence.upload_status,
            original_filename=evidence.original_filename,
            content_type=evidence.content_type,
            size_bytes=evidence.size_bytes,
            sha256=evidence.sha256,
            width=evidence.width,
            height=evidence.height,
            created_by=evidence.created_by,
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
        )


class EvidenceListResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    items: tuple[EvidenceResponse, ...]


class EvidenceAccessUrlResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    evidence_id: str
    url: str = Field(min_length=1, repr=False)
    expires_at: datetime

    @classmethod
    def from_result(cls, result: EvidenceAccessUrl) -> Self:
        return cls(
            evidence_id=result.evidence_id,
            url=result.url,
            expires_at=result.expires_at,
        )


class CaseDetailResponse(BaseModel):
    model_config = SPRINT1_MODEL_CONFIG

    case_id: str
    tenant_id: str
    domain_type: DomainType
    status: CaseStatus
    order_ref: str
    product_ref: str
    customer_message: str = Field(repr=False)
    requested_action: RequestedAction
    attributes: dict[str, JsonValue]
    created_by: str
    created_at: datetime
    updated_at: datetime
    evidence: tuple[EvidenceResponse, ...]
    status_history: tuple[StatusHistoryResponse, ...]
    latest_analysis_run: AnalysisRunResponse | None = None

    @classmethod
    def from_domain(
        cls,
        *,
        case: Case,
        evidence: tuple[EvidenceMetadata, ...],
        history: tuple[CaseStatusTransition, ...],
        latest_analysis_run: AnalysisRun | None = None,
    ) -> Self:
        return cls(
            case_id=case.id,
            tenant_id=case.tenant_id,
            domain_type=case.domain_type,
            status=case.status,
            order_ref=case.order_ref,
            product_ref=case.product_ref,
            customer_message=case.customer_message,
            requested_action=case.requested_action,
            attributes=case.attributes,
            created_by=case.created_by,
            created_at=case.created_at,
            updated_at=case.updated_at,
            evidence=tuple(EvidenceResponse.from_evidence(item) for item in evidence),
            status_history=tuple(StatusHistoryResponse.from_transition(item) for item in history),
            latest_analysis_run=(
                AnalysisRunResponse.from_run(latest_analysis_run)
                if latest_analysis_run is not None
                else None
            ),
        )
