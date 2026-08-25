"""Deterministic, network-free LLM adapter used in Sprint 0."""

from pydantic import ValidationError

from app.platform.analysis import (
    CustomerRequest,
    DefectLocation,
    DefectType,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    LLMClaim,
    MockProviderMode,
    ProviderFailureError,
    ProviderMetadata,
    ProviderSchemaError,
    ProviderTimeoutError,
)


class MockLLMProvider:
    """A contract-realistic fake with explicit deterministic failure scenarios."""

    def __init__(
        self,
        *,
        mode: MockProviderMode | str = MockProviderMode.SUCCESS,
        model_name: str = "csight-mock-llm",
        model_version: str = "0.1.0",
    ) -> None:
        normalized_mode = mode.replace("-", "_")
        self._mode = MockProviderMode(normalized_mode)
        self._metadata = ProviderMetadata(
            provider="mock",
            name=model_name,
            version=model_version,
        )

    @property
    def provider_metadata(self) -> ProviderMetadata:
        return self._metadata

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        self._raise_configured_failure()
        if self._mode is MockProviderMode.SCHEMA_ERROR:
            self._raise_schema_error()

        text = request.customer_message.casefold()
        issue_type = self._detect_issue_type(text)
        location = self._detect_location(text)
        customer_request = self._detect_customer_request(text, request.requested_action)

        claims = self._build_claims(text, issue_type)
        missing_information: list[str] = []
        if location is DefectLocation.UNKNOWN:
            missing_information.append("defect_location")
        if customer_request is CustomerRequest.UNSPECIFIED:
            missing_information.append("customer_request")

        return LLMCaseExtraction(
            model=self._metadata,
            issue_type=issue_type,
            claimed_location=location,
            customer_request=customer_request,
            claims=claims,
            missing_information=tuple(missing_information),
            summary=f"Mock extraction identified {issue_type.value} for case {request.case_id}.",
        )

    def _raise_configured_failure(self) -> None:
        if self._mode is MockProviderMode.TIMEOUT:
            raise ProviderTimeoutError(
                provider=self._metadata.provider,
                message="mock LLM deadline exceeded",
            )
        if self._mode is MockProviderMode.FAILURE:
            raise ProviderFailureError(
                provider=self._metadata.provider,
                message="mock LLM inference failed",
            )

    def _raise_schema_error(self) -> None:
        try:
            LLMCaseExtraction.model_validate(
                {
                    "schema_version": "unsupported",
                    "model": self._metadata.model_dump(),
                    "issue_type": "PROVIDER_CLASS_17",
                    "claimed_location": "UNKNOWN",
                    "customer_request": "UNSPECIFIED",
                    "summary": "invalid provider payload",
                }
            )
        except ValidationError as error:
            raise ProviderSchemaError(
                provider=self._metadata.provider,
                message="mock LLM response violated the common schema",
            ) from error
        raise AssertionError("mock schema-error payload unexpectedly validated")

    @staticmethod
    def _detect_issue_type(text: str) -> DefectType:
        if any(token in text for token in ("누액", "누출", "샜", "leak")):
            return DefectType.LEAKAGE
        if any(token in text for token in ("찌그러", "용기 파손", "container damage", "dent")):
            return DefectType.CONTAINER_DAMAGE
        if any(token in text for token in ("균열", "금이", "crack")):
            return DefectType.CRACK
        if any(token in text for token in ("긁", "스크래치", "scratch")):
            return DefectType.SCRATCH
        return DefectType.UNKNOWN

    @staticmethod
    def _detect_location(text: str) -> DefectLocation:
        locations = (
            (("하단", "바닥", "bottom"), DefectLocation.BOTTOM),
            (("상단", "위쪽", "top"), DefectLocation.TOP),
            (("측면", "옆면", "side"), DefectLocation.SIDE),
            (("앞면", "front"), DefectLocation.FRONT),
            (("뒷면", "back"), DefectLocation.BACK),
            (("내부", "inside"), DefectLocation.INSIDE),
            (("외부", "outside"), DefectLocation.OUTSIDE),
        )
        return next(
            (location for tokens, location in locations if any(token in text for token in tokens)),
            DefectLocation.UNKNOWN,
        )

    @staticmethod
    def _detect_customer_request(
        text: str,
        requested_action: CustomerRequest,
    ) -> CustomerRequest:
        if requested_action is not CustomerRequest.UNSPECIFIED:
            return requested_action
        requests = (
            (("교환", "exchange"), CustomerRequest.EXCHANGE),
            (("환불", "refund"), CustomerRequest.REFUND),
            (("반품", "return"), CustomerRequest.RETURN),
            (("수리", "repair"), CustomerRequest.REPAIR),
        )
        return next(
            (request for tokens, request in requests if any(token in text for token in tokens)),
            CustomerRequest.UNSPECIFIED,
        )

    @staticmethod
    def _build_claims(text: str, issue_type: DefectType) -> tuple[LLMClaim, ...]:
        claims: list[LLMClaim] = []
        if any(token in text for token in ("찌그러", "용기 파손", "container damage", "dent")):
            claims.append(
                LLMClaim(
                    type=DefectType.CONTAINER_DAMAGE,
                    description="The customer reports container damage.",
                )
            )
        if any(token in text for token in ("누액", "누출", "샜", "leak")):
            claims.append(
                LLMClaim(
                    type=DefectType.LEAKAGE,
                    description="The customer reports product leakage.",
                )
            )
        if not claims:
            claims.append(
                LLMClaim(
                    type=issue_type,
                    description="The customer reports an unspecified product issue.",
                )
            )
        return tuple(claims)
