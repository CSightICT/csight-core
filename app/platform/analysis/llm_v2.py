"""Decision-free LLM extraction v2 and deterministic completeness rules."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis.enums import CustomerRequest, DefectLocation, ExtractionIssueType
from app.platform.analysis.errors import LLMSourceQuoteMismatchError
from app.platform.analysis.models import ProviderExecutionMetadata


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TextAmbiguity(StrEnum):
    DEFECT_TYPE_UNCLEAR = "DEFECT_TYPE_UNCLEAR"
    DEFECT_LOCATION_UNCLEAR = "DEFECT_LOCATION_UNCLEAR"
    REQUEST_UNCLEAR = "REQUEST_UNCLEAR"
    MULTIPLE_CONFLICTING_REQUESTS = "MULTIPLE_CONFLICTING_REQUESTS"
    DESCRIPTION_TOO_VAGUE = "DESCRIPTION_TOO_VAGUE"
    CONTRADICTORY_STATEMENTS = "CONTRADICTORY_STATEMENTS"


class SystemMissingInformation(StrEnum):
    ORDER_REFERENCE = "ORDER_REFERENCE"
    PRODUCT_REFERENCE = "PRODUCT_REFERENCE"
    IMAGE_EVIDENCE = "IMAGE_EVIDENCE"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"


class ActionConsistency(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    ONLY_DECLARED = "ONLY_DECLARED"
    ONLY_EXTRACTED = "ONLY_EXTRACTED"
    BOTH_UNSPECIFIED = "BOTH_UNSPECIFIED"
    MULTIPLE_EXTRACTED = "MULTIPLE_EXTRACTED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ExtractedActionV2(StrEnum):
    REFUND = "REFUND"
    EXCHANGE = "EXCHANGE"
    RESHIPMENT = "RESHIPMENT"
    REPAIR = "REPAIR"
    INFORMATION = "INFORMATION"
    OTHER = "OTHER"


class LLMTextExtractionRequestV2(_StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    customer_message: str = Field(min_length=1, max_length=20_000, repr=False)
    order_ref: str | None = Field(default=None, max_length=200)
    product_ref: str | None = Field(default=None, max_length=200)
    declared_requested_action: CustomerRequest = CustomerRequest.UNSPECIFIED


class LLMTextClaimV2(_StrictModel):
    type: ExtractionIssueType
    location: DefectLocation = DefectLocation.UNKNOWN
    description: str = Field(min_length=1, max_length=2_000)
    source_quote: str = Field(min_length=1, max_length=2_000, repr=False)


class RequestedActionItemV2(_StrictModel):
    action: ExtractedActionV2
    source_quote: str = Field(min_length=1, max_length=2_000, repr=False)


class LLMTextExtractionResultV2(_StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    language: str = Field(default="ko", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    issue_types: tuple[ExtractionIssueType, ...] = Field(default=(), max_length=20)
    claims: tuple[LLMTextClaimV2, ...] = Field(default=(), max_length=50)
    requested_actions: tuple[RequestedActionItemV2, ...] = Field(default=(), max_length=10)
    text_ambiguities: tuple[TextAmbiguity, ...] = Field(default=(), max_length=10)
    summary: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_sets_and_claims(self) -> "LLMTextExtractionResultV2":
        for values, field_name in (
            (self.issue_types, "issue_types"),
            (self.text_ambiguities, "text_ambiguities"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if {claim.type for claim in self.claims} - set(self.issue_types):
            raise ValueError("every claim type must also appear in issue_types")
        action_quotes = {(item.action, item.source_quote) for item in self.requested_actions}
        if len(action_quotes) != len(self.requested_actions):
            raise ValueError("requested_actions must not contain duplicates")
        return self

    def require_exact_source_quotes(self, *, customer_message: str, provider: str) -> None:
        quotes = tuple(claim.source_quote for claim in self.claims) + tuple(
            item.source_quote for item in self.requested_actions
        )
        if any(quote not in customer_message for quote in quotes):
            raise LLMSourceQuoteMismatchError(
                provider=provider,
                message="a v2 source quote was not an exact customer-message substring",
            )


class LLMTextExtractionResponseV2(_StrictModel):
    result: LLMTextExtractionResultV2
    metadata: ProviderExecutionMetadata


class CompletenessInput(_StrictModel):
    order_ref: str | None
    product_ref: str | None
    declared_requested_action: CustomerRequest
    available_image_count: int = Field(ge=0)
    extracted_actions: tuple[ExtractedActionV2, ...] = ()


class CompletenessResult(_StrictModel):
    rule_version: Literal["1.0.0"] = "1.0.0"
    system_missing_information: tuple[SystemMissingInformation, ...]
    action_consistency: ActionConsistency


def evaluate_completeness(value: CompletenessInput) -> CompletenessResult:
    missing: list[SystemMissingInformation] = []
    if not value.order_ref or not value.order_ref.strip():
        missing.append(SystemMissingInformation.ORDER_REFERENCE)
    if not value.product_ref or not value.product_ref.strip():
        missing.append(SystemMissingInformation.PRODUCT_REFERENCE)
    if value.available_image_count == 0:
        missing.append(SystemMissingInformation.IMAGE_EVIDENCE)
    declared = value.declared_requested_action
    extracted = value.extracted_actions
    if declared is CustomerRequest.UNSPECIFIED and not extracted:
        missing.append(SystemMissingInformation.CUSTOMER_REQUEST)
    return CompletenessResult(
        system_missing_information=tuple(missing),
        action_consistency=evaluate_action_consistency(declared=declared, extracted=extracted),
    )


def evaluate_action_consistency(
    *, declared: CustomerRequest, extracted: tuple[ExtractedActionV2, ...]
) -> ActionConsistency:
    if len(extracted) > 1:
        return ActionConsistency.MULTIPLE_EXTRACTED
    declared_unspecified = declared is CustomerRequest.UNSPECIFIED
    if declared_unspecified and not extracted:
        return ActionConsistency.BOTH_UNSPECIFIED
    if declared_unspecified:
        return ActionConsistency.ONLY_EXTRACTED
    if not extracted:
        return ActionConsistency.ONLY_DECLARED
    comparable = {
        CustomerRequest.REFUND: ExtractedActionV2.REFUND,
        CustomerRequest.EXCHANGE: ExtractedActionV2.EXCHANGE,
        CustomerRequest.REPAIR: ExtractedActionV2.REPAIR,
        CustomerRequest.INFORMATION: ExtractedActionV2.INFORMATION,
        CustomerRequest.OTHER: ExtractedActionV2.OTHER,
    }
    expected = comparable.get(declared)
    if expected is None:
        return ActionConsistency.NOT_COMPARABLE
    return ActionConsistency.MATCH if extracted[0] is expected else ActionConsistency.MISMATCH


class LLMExtractionResultV2Record(_StrictModel):
    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    stage_run_id: str = Field(min_length=1)
    result: LLMTextExtractionResultV2
    completeness: CompletenessResult
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class PolicyQueryFilters(_StrictModel):
    policy_types: tuple[str, ...] = ()
    product_categories: tuple[str, ...] = ()
    defect_types: tuple[ExtractionIssueType, ...] = ()
    document_status: Literal["ACTIVE"] = "ACTIVE"


class PolicyQueryBuilderResult(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    queries: tuple[str, ...] = Field(min_length=1, max_length=5)
    filters: PolicyQueryFilters


class ApplicablePolicyEvidence(_StrictModel):
    clause_id: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class GroundedPolicyExplanation(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    applicable_evidence: tuple[ApplicablePolicyEvidence, ...]
    unresolved_conditions: tuple[str, ...] = ()

    def require_allowed_citations(self, allowed_clause_ids: set[str]) -> None:
        if any(item.clause_id not in allowed_clause_ids for item in self.applicable_evidence):
            raise ValueError("all clause IDs must exist in the supplied retrieval context")
