"""Deterministic, network-free LLM adapter used in Sprint 0."""

import hashlib

from pydantic import ValidationError

from app.platform.analysis import (
    CustomerRequest,
    DefectLocation,
    DefectType,
    ExtractedRequestedAction,
    ExtractionIssueType,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    LLMClaim,
    LLMInvalidStructuredOutputError,
    LLMProviderRequestRejectedError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    LLMTextClaim,
    LLMTextExtractionRequest,
    LLMTextExtractionResponse,
    LLMTextExtractionResult,
    MissingInformation,
    MockProviderMode,
    ProviderExecutionMetadata,
    ProviderFailureError,
    ProviderMetadata,
    ProviderSchemaError,
    ProviderTimeoutError,
)
from app.platform.analysis.prompts import PromptManifest


class MockLLMProvider:
    """A contract-realistic fake with explicit deterministic failure scenarios."""

    def __init__(
        self,
        *,
        mode: MockProviderMode | str = MockProviderMode.SUCCESS,
        model_name: str = "csight-mock-llm",
        model_version: str = "0.1.0",
        model_revision: str = "deterministic",
    ) -> None:
        normalized_mode = mode.replace("-", "_")
        self._mode = MockProviderMode(normalized_mode)
        self._metadata = ProviderMetadata(
            provider="mock",
            name=model_name,
            version=model_version,
            revision=model_revision,
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

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        """Produce deterministic Sprint 2 output without exposing customer content."""

        self._raise_configured_text_failure()
        if self._mode in {MockProviderMode.SCHEMA_ERROR, MockProviderMode.INVALID_SCHEMA}:
            raise LLMInvalidStructuredOutputError(
                provider=self._metadata.provider,
                message="mock LLM response violated the text extraction schema",
            )
        if prompt.input_schema_version != request.schema_version:
            raise LLMProviderRequestRejectedError(
                provider=self._metadata.provider,
                message="prompt input schema does not match the request schema",
            )

        # Rendering exercises the same JSON-escaping boundary used by remote
        # adapters. The rendered prompt is deliberately neither logged nor returned.
        prompt.render_user(request.model_dump(mode="json"))
        result = self._build_text_result(request)
        if prompt.output_schema_version != result.schema_version:
            raise LLMProviderRequestRejectedError(
                provider=self._metadata.provider,
                message="prompt output schema does not match the result schema",
            )
        if self._mode is MockProviderMode.INVALID_SOURCE_QUOTE:
            result = self._with_invalid_source_quote(result)
        result.require_exact_source_quotes(
            customer_message=request.customer_message,
            provider=self._metadata.provider,
        )
        serialized_result = result.model_dump_json()
        request_fingerprint = hashlib.sha256(request.customer_message.encode("utf-8")).hexdigest()
        return LLMTextExtractionResponse(
            result=result,
            metadata=ProviderExecutionMetadata(
                provider_name=self._metadata.provider,
                model_name=self._metadata.name,
                model_version=self._metadata.version,
                model_revision=self._metadata.revision,
                provider_request_id=f"mock-{request_fingerprint[:16]}",
                input_token_count=max(1, len(request.customer_message.split())),
                output_token_count=max(1, len(serialized_result) // 4),
                latency_ms=0,
            ),
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

    def _raise_configured_text_failure(self) -> None:
        if self._mode is MockProviderMode.TIMEOUT:
            raise LLMProviderTimeoutError(
                provider=self._metadata.provider,
                message="mock LLM deadline exceeded",
            )
        if self._mode in {MockProviderMode.FAILURE, MockProviderMode.TRANSIENT_ERROR}:
            raise LLMProviderUnavailableError(
                provider=self._metadata.provider,
                message="mock LLM is temporarily unavailable",
            )
        if self._mode is MockProviderMode.PERMANENT_ERROR:
            raise LLMProviderRequestRejectedError(
                provider=self._metadata.provider,
                message="mock LLM permanently rejected the request",
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

    def _build_text_result(
        self,
        request: LLMTextExtractionRequest,
    ) -> LLMTextExtractionResult:
        if self._looks_like_prompt_injection(request.customer_message):
            return LLMTextExtractionResult(
                language="ko",
                issue_types=(ExtractionIssueType.UNKNOWN,),
                requested_action=ExtractedRequestedAction.UNKNOWN,
                missing_information=(
                    MissingInformation.DEFECT_TYPE,
                    MissingInformation.DEFECT_LOCATION,
                    MissingInformation.CUSTOMER_REQUEST,
                ),
                summary="고객 메시지에서 명확한 상품 결함 주장을 확인할 수 없습니다.",
            )

        findings = self._text_findings(request.customer_message)
        issue_types = tuple(issue_type for issue_type, _quote in findings)
        if not issue_types:
            issue_types = (ExtractionIssueType.UNKNOWN,)
        location = self._detect_location(request.customer_message.casefold())
        claims = tuple(
            LLMTextClaim(
                type=issue_type,
                location=location,
                description=self._claim_description(issue_type),
                source_quote=quote,
            )
            for issue_type, quote in findings
        )
        requested_action = self._extracted_action(request)
        missing: list[MissingInformation] = []
        if issue_types == (ExtractionIssueType.UNKNOWN,):
            missing.append(MissingInformation.DEFECT_TYPE)
        if location is DefectLocation.UNKNOWN:
            missing.append(MissingInformation.DEFECT_LOCATION)
        if requested_action is ExtractedRequestedAction.UNKNOWN:
            missing.append(MissingInformation.CUSTOMER_REQUEST)
        if issue_types == (ExtractionIssueType.UNKNOWN,):
            summary = "고객 메시지에서 명확한 상품 결함 주장을 확인할 수 없습니다."
        else:
            rendered_types = ", ".join(issue_type.value for issue_type in issue_types)
            summary = f"고객은 {rendered_types} 관련 상품 문제를 주장했습니다."
        return LLMTextExtractionResult(
            language="ko",
            issue_types=issue_types,
            claims=claims,
            requested_action=requested_action,
            missing_information=tuple(missing),
            summary=summary,
        )

    @staticmethod
    def _looks_like_prompt_injection(message: str) -> bool:
        normalized = message.casefold()
        markers = (
            "이전 지시를 무시",
            "관리자 권한",
            "시스템 프롬프트",
            "정책을 무시",
            "ignore previous",
            "system prompt",
            "administrator privileges",
        )
        return any(marker in normalized for marker in markers)

    @classmethod
    def _text_findings(
        cls,
        message: str,
    ) -> tuple[tuple[ExtractionIssueType, str], ...]:
        candidates = (
            (
                ExtractionIssueType.PACKAGING_DAMAGE,
                ("포장 파손", "포장이 손상", "packaging damage"),
            ),
            (ExtractionIssueType.DENT, ("찌그러", "dent")),
            (ExtractionIssueType.CRACK, ("균열", "금이", "crack")),
            (ExtractionIssueType.BREAKAGE, ("깨졌", "파손", "breakage")),
            (ExtractionIssueType.LEAKAGE, ("누액", "누출", "샜", "leak")),
            (
                ExtractionIssueType.MISSING_COMPONENT,
                ("구성품 누락", "부품 누락", "missing component"),
            ),
            (ExtractionIssueType.WRONG_ITEM, ("다른 상품", "오배송", "wrong item")),
            (ExtractionIssueType.CONTAMINATION, ("오염", "이물질", "contamination")),
            (ExtractionIssueType.FUNCTIONAL_FAILURE, ("작동하지", "고장", "functional failure")),
        )
        findings: list[tuple[ExtractionIssueType, str]] = []
        claimed_spans: set[str] = set()
        for issue_type, tokens in candidates:
            quote = cls._first_exact_token(message, tokens)
            if quote is not None and quote not in claimed_spans:
                findings.append((issue_type, quote))
                claimed_spans.add(quote)
        return tuple(findings)

    @staticmethod
    def _first_exact_token(message: str, tokens: tuple[str, ...]) -> str | None:
        normalized = message.casefold()
        for token in tokens:
            index = normalized.find(token.casefold())
            if index >= 0:
                return message[index : index + len(token)]
        return None

    @staticmethod
    def _claim_description(issue_type: ExtractionIssueType) -> str:
        descriptions = {
            ExtractionIssueType.DENT: "고객이 상품의 찌그러짐을 주장함",
            ExtractionIssueType.CRACK: "고객이 상품의 균열을 주장함",
            ExtractionIssueType.BREAKAGE: "고객이 상품의 파손을 주장함",
            ExtractionIssueType.LEAKAGE: "고객이 내용물 누출을 주장함",
            ExtractionIssueType.MISSING_COMPONENT: "고객이 구성품 누락을 주장함",
            ExtractionIssueType.WRONG_ITEM: "고객이 주문과 다른 상품을 주장함",
            ExtractionIssueType.CONTAMINATION: "고객이 상품 오염을 주장함",
            ExtractionIssueType.FUNCTIONAL_FAILURE: "고객이 상품 기능 불량을 주장함",
            ExtractionIssueType.PACKAGING_DAMAGE: "고객이 포장 손상을 주장함",
            ExtractionIssueType.OTHER: "고객이 기타 상품 문제를 주장함",
            ExtractionIssueType.UNKNOWN: "고객이 구체적이지 않은 상품 문제를 주장함",
        }
        return descriptions[issue_type]

    @staticmethod
    def _extracted_action(request: LLMTextExtractionRequest) -> ExtractedRequestedAction:
        hint_mapping = {
            CustomerRequest.EXCHANGE: ExtractedRequestedAction.EXCHANGE,
            CustomerRequest.REFUND: ExtractedRequestedAction.REFUND,
            CustomerRequest.REPAIR: ExtractedRequestedAction.REPAIR,
            CustomerRequest.INFORMATION: ExtractedRequestedAction.INFORMATION,
            CustomerRequest.OTHER: ExtractedRequestedAction.OTHER,
            CustomerRequest.RETURN: ExtractedRequestedAction.OTHER,
        }
        if request.requested_action in hint_mapping:
            return hint_mapping[request.requested_action]
        text = request.customer_message.casefold()
        requests = (
            (("교환", "exchange"), ExtractedRequestedAction.EXCHANGE),
            (("환불", "refund"), ExtractedRequestedAction.REFUND),
            (("재배송", "다시 보내", "reship"), ExtractedRequestedAction.RESHIPMENT),
            (("수리", "repair"), ExtractedRequestedAction.REPAIR),
            (("문의", "알려", "information"), ExtractedRequestedAction.INFORMATION),
        )
        return next(
            (action for tokens, action in requests if any(token in text for token in tokens)),
            ExtractedRequestedAction.UNKNOWN,
        )

    @staticmethod
    def _with_invalid_source_quote(
        result: LLMTextExtractionResult,
    ) -> LLMTextExtractionResult:
        if result.claims:
            claims = (
                result.claims[0].model_copy(update={"source_quote": "원문에 없는 인용문"}),
                *result.claims[1:],
            )
        else:
            claims = (
                LLMTextClaim(
                    type=ExtractionIssueType.UNKNOWN,
                    location=DefectLocation.UNKNOWN,
                    description="고객이 구체적이지 않은 상품 문제를 주장함",
                    source_quote="원문에 없는 인용문",
                ),
            )
        issue_types = result.issue_types
        if claims[0].type not in issue_types:
            issue_types = (*issue_types, claims[0].type)
        return LLMTextExtractionResult(
            schema_version=result.schema_version,
            language=result.language,
            issue_types=issue_types,
            claims=claims,
            requested_action=result.requested_action,
            missing_information=result.missing_information,
            summary=result.summary,
        )

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
