"""Strict vLLM adapter for OpenAI-compatible structured text extraction."""

import json
import ssl
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, NoReturn, Protocol, cast
from urllib.parse import urlsplit

import urllib3
from pydantic import ValidationError
from urllib3 import Timeout
from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    MaxRetryError,
    NewConnectionError,
    ReadTimeoutError,
)
from urllib3.exceptions import (
    TimeoutError as Urllib3TimeoutError,
)
from urllib3.response import BaseHTTPResponse

from app.platform.analysis.errors import (
    LLMInvalidStructuredOutputError,
    LLMProviderAuthenticationError,
    LLMProviderRequestRejectedError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from app.platform.analysis.llm_v2 import (
    LLMTextExtractionRequestV2,
    LLMTextExtractionResponseV2,
    LLMTextExtractionResultV2,
)
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.analysis.prompts import PromptManifest
from app.platform.analysis.schemas import (
    SCHEMA_VERSION,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    LLMTextExtractionRequest,
    LLMTextExtractionResponse,
    LLMTextExtractionResult,
    ProviderMetadata,
)
from app.platform.query_builder import (
    PolicyQueryBuilderInput,
    PolicyQueryBuilderInvalidOutputError,
    PolicyQueryBuilderResponse,
    PolicyQueryPlan,
)

_PROVIDER_NAME = "vllm"
_RESPONSE_SCHEMA_NAME = "csight_text_extraction"
_RESPONSE_ENVELOPE_ALLOWANCE_BYTES = 64 * 1024


class _HTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        fields: object | None = None,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        **urlopen_kw: Any,
    ) -> BaseHTTPResponse: ...


class VLLMLLMProvider:
    """Call one configured vLLM deployment and normalize its strict JSON result."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_id: str,
        model_version: str,
        model_revision: str | None,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_output_tokens: int,
        max_output_chars: int,
        max_input_chars: int,
        temperature: float,
        tls_verify: bool,
        http_client: _HTTPClient | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._endpoint = _chat_completions_endpoint(base_url)
        self._model_id = _bounded_non_empty("model_id", model_id, max_length=255)
        self._model_version = _bounded_non_empty("model_version", model_version, max_length=100)
        self._model_revision = _optional_bounded_non_empty(
            "model_revision", model_revision, max_length=255
        )
        self._api_key = _optional_non_empty("api_key", api_key)
        self._connect_timeout_seconds = _positive(
            "connect_timeout_seconds", connect_timeout_seconds
        )
        self._read_timeout_seconds = _positive("read_timeout_seconds", read_timeout_seconds)
        self._max_output_tokens = _positive_int("max_output_tokens", max_output_tokens)
        self._max_output_chars = _positive_int("max_output_chars", max_output_chars)
        self._max_input_chars = _positive_int("max_input_chars", max_input_chars)
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        self._temperature = temperature
        self._max_response_bytes = self._max_output_chars * 4 + _RESPONSE_ENVELOPE_ALLOWANCE_BYTES
        self._clock = clock
        if http_client is None:
            cert_reqs = ssl.CERT_REQUIRED if tls_verify else ssl.CERT_NONE
            http_client = cast(
                _HTTPClient,
                urllib3.PoolManager(cert_reqs=cert_reqs),
            )
        self._http_client = http_client

    @property
    def provider_metadata(self) -> ProviderMetadata:
        """Retain the legacy provider identity used by the Sprint 0 contract."""

        return ProviderMetadata(
            provider=_PROVIDER_NAME,
            name=self._model_id,
            version=self._model_version,
            revision=self._model_revision,
        )

    def extract_case(self, request: LLMAnalysisRequest) -> LLMCaseExtraction:
        """Reject the legacy unversioned prompt path instead of inventing a prompt."""

        del request
        raise LLMProviderRequestRejectedError(
            provider=_PROVIDER_NAME,
            message="the legacy extraction operation is not supported by the vLLM adapter",
        )

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        """Render allowlisted input, request strict JSON, and return trusted metadata."""

        self._validate_prompt_contract(request=request, prompt=prompt)
        input_data: dict[str, object] = {
            "schema_version": request.schema_version,
            "customer_message": request.customer_message,
            "order_ref": request.order_ref,
            "product_ref": request.product_ref,
            "requested_action": request.requested_action.value,
        }
        try:
            user_message = prompt.render_user(input_data)
        except (TypeError, ValueError):
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the configured prompt could not render the structured input",
            ) from None
        if len(request.customer_message) > self._max_input_chars:
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the customer input exceeds the configured character limit",
            )

        payload = self._request_payload(
            system_message=prompt.system_template,
            user_message=user_message,
            schema=LLMTextExtractionResult.model_json_schema(),
        )
        started_at = self._clock()
        status, provider_request_id, raw_response = self._post(payload)
        latency_ms = max(0, round((self._clock() - started_at) * 1000))
        self._raise_for_status(status)
        decoded = _decode_json_object(raw_response)
        content = _choice_content(decoded, max_chars=self._max_output_chars)
        result = _decode_structured_result(content)
        result.require_exact_source_quotes(
            customer_message=request.customer_message,
            provider=_PROVIDER_NAME,
        )
        input_tokens, output_tokens = _usage(decoded)
        body_request_id = _optional_request_id(decoded.get("id"))

        return LLMTextExtractionResponse(
            result=result,
            metadata=ProviderExecutionMetadata(
                provider_name=_PROVIDER_NAME,
                model_name=self._model_id,
                model_version=self._model_version,
                model_revision=self._model_revision,
                provider_request_id=provider_request_id or body_request_id,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
                latency_ms=latency_ms,
            ),
        )

    def extract_text_v2(
        self,
        request: LLMTextExtractionRequestV2,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponseV2:
        if prompt.input_schema_version != "2.0" or prompt.output_schema_version != "2.0":
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the prompt does not match extraction schema v2",
            )
        input_data: dict[str, object] = request.model_dump(mode="json")
        try:
            user_message = prompt.render_user(input_data)
        except (TypeError, ValueError):
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the configured v2 prompt could not render structured input",
            ) from None
        if len(request.customer_message) > self._max_input_chars:
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the customer input exceeds the configured character limit",
            )
        payload = self._request_payload(
            system_message=prompt.system_template,
            user_message=user_message,
            schema=LLMTextExtractionResultV2.model_json_schema(),
        )
        started_at = self._clock()
        status, provider_request_id, raw_response = self._post(payload)
        latency_ms = max(0, round((self._clock() - started_at) * 1000))
        self._raise_for_status(status)
        decoded = _decode_json_object(raw_response)
        content = _choice_content(decoded, max_chars=self._max_output_chars)
        try:
            result = LLMTextExtractionResultV2.model_validate_json(content)
        except (ValueError, ValidationError):
            raise LLMInvalidStructuredOutputError(
                provider=_PROVIDER_NAME,
                message="the vLLM response did not match extraction schema v2",
            ) from None
        result.require_exact_source_quotes(
            customer_message=request.customer_message,
            provider=_PROVIDER_NAME,
        )
        input_tokens, output_tokens = _usage(decoded)
        body_request_id = _optional_request_id(decoded.get("id"))
        return LLMTextExtractionResponseV2(
            result=result,
            metadata=ProviderExecutionMetadata(
                provider_name=_PROVIDER_NAME,
                model_name=self._model_id,
                model_version=self._model_version,
                model_revision=self._model_revision,
                provider_request_id=provider_request_id or body_request_id,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
                latency_ms=latency_ms,
            ),
        )

    def build_policy_queries(
        self,
        request: PolicyQueryBuilderInput,
        prompt: PromptManifest,
    ) -> PolicyQueryBuilderResponse:
        """Generate a strict query plan without sending the original customer message."""

        if prompt.name != "policy_query_builder" or (
            prompt.input_schema_version != "1.0" or prompt.output_schema_version != "1.0"
        ):
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the prompt does not match policy query schema v1",
            )
        input_data = request.model_dump(mode="json")
        user_message = prompt.render_user(input_data)
        if len(user_message) > self._max_input_chars:
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the structured query input exceeds the configured character limit",
            )
        payload = self._request_payload(
            system_message=prompt.system_template,
            user_message=user_message,
            schema=PolicyQueryPlan.model_json_schema(),
        )
        started_at = self._clock()
        status, provider_request_id, raw_response = self._post(payload)
        latency_ms = max(0, round((self._clock() - started_at) * 1000))
        self._raise_for_status(status)
        decoded = _decode_json_object(raw_response)
        content = _choice_content(decoded, max_chars=self._max_output_chars)
        try:
            plan = PolicyQueryPlan.model_validate_json(content)
        except (ValueError, ValidationError):
            raise PolicyQueryBuilderInvalidOutputError() from None
        input_tokens, output_tokens = _usage(decoded)
        body_request_id = _optional_request_id(decoded.get("id"))
        return PolicyQueryBuilderResponse(
            plan=plan,
            metadata=ProviderExecutionMetadata(
                provider_name=_PROVIDER_NAME,
                model_name=self._model_id,
                model_version=self._model_version,
                model_revision=self._model_revision,
                provider_request_id=provider_request_id or body_request_id,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
                latency_ms=latency_ms,
            ),
        )

    def _validate_prompt_contract(
        self,
        *,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> None:
        if prompt.input_schema_version != request.schema_version:
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the prompt input schema version does not match the request",
            )
        if prompt.output_schema_version != SCHEMA_VERSION:
            raise LLMProviderRequestRejectedError(
                provider=_PROVIDER_NAME,
                message="the prompt output schema version is not supported",
            )

    def _request_payload(
        self,
        *,
        system_message: str,
        user_message: str,
        schema: dict[str, Any],
    ) -> dict[str, object]:
        return {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
            "stream": False,
            "chat_template_kwargs": {
                "enable_thinking": False,
                "preserve_thinking": False,
            },
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _RESPONSE_SCHEMA_NAME,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

    def _post(self, payload: Mapping[str, object]) -> tuple[int, str | None, bytes]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
        }
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            encoded_payload = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            response = self._http_client.request(
                "POST",
                self._endpoint,
                body=encoded_payload,
                headers=headers,
                timeout=Timeout(
                    connect=self._connect_timeout_seconds,
                    read=self._read_timeout_seconds,
                ),
                retries=False,
                redirect=False,
                preload_content=False,
            )
        except NewConnectionError:
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message="the vLLM service could not be reached",
            ) from None
        except (ConnectTimeoutError, ReadTimeoutError, Urllib3TimeoutError):
            raise LLMProviderTimeoutError(
                provider=_PROVIDER_NAME,
                message="the vLLM request exceeded its configured deadline",
            ) from None
        except MaxRetryError as error:
            if isinstance(error.reason, NewConnectionError):
                raise LLMProviderUnavailableError(
                    provider=_PROVIDER_NAME,
                    message="the vLLM service could not be reached",
                ) from None
            if isinstance(error.reason, Urllib3TimeoutError):
                raise LLMProviderTimeoutError(
                    provider=_PROVIDER_NAME,
                    message="the vLLM request exceeded its configured deadline",
                ) from None
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message="the vLLM service could not be reached",
            ) from None
        except (HTTPError, OSError):
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message="the vLLM service could not be reached",
            ) from None

        try:
            status = response.status
            request_id = _header_request_id(response.headers)
            body = response.read(
                amt=self._max_response_bytes + 1,
                decode_content=False,
                cache_content=False,
            )
        except (HTTPError, OSError):
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message="the vLLM response could not be read",
            ) from None
        finally:
            response.release_conn()
        if 200 <= status < 300 and len(body) > self._max_response_bytes:
            raise LLMInvalidStructuredOutputError(
                provider=_PROVIDER_NAME,
                message="the vLLM response exceeded the configured size limit",
            )
        return status, request_id, body

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise LLMProviderAuthenticationError(
                provider=_PROVIDER_NAME,
                message="the vLLM service rejected its configured credentials",
            )
        if status == 429 or status >= 500:
            raise LLMProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message=f"the vLLM service is unavailable (HTTP {status})",
            )
        raise LLMProviderRequestRejectedError(
            provider=_PROVIDER_NAME,
            message=f"the vLLM service rejected the request (HTTP {status})",
        )


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url must be an HTTP(S) origin without credentials or query data")
    if parsed.path.rstrip("/") == "/v1":
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _non_empty(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


def _bounded_non_empty(name: str, value: str, *, max_length: int) -> str:
    normalized = _non_empty(name, value)
    if len(normalized) > max_length:
        raise ValueError(f"{name} must not exceed {max_length} characters")
    return normalized


def _optional_non_empty(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _non_empty(name, value)


def _optional_bounded_non_empty(
    name: str,
    value: str | None,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    return _bounded_non_empty(name, value, max_length=max_length)


def _positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _reject_non_standard_json(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _decode_json(value: str) -> object:
    return json.loads(
        value,
        parse_constant=_reject_non_standard_json,
        object_pairs_hook=_unique_object,
    )


def _decode_json_object(raw_response: bytes) -> dict[str, object]:
    try:
        decoded_text = raw_response.decode("utf-8", errors="strict")
        decoded = _decode_json(decoded_text)
    except (UnicodeDecodeError, ValueError):
        raise LLMInvalidStructuredOutputError(
            provider=_PROVIDER_NAME,
            message="the vLLM response was not valid UTF-8 JSON",
        ) from None
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        raise LLMInvalidStructuredOutputError(
            provider=_PROVIDER_NAME,
            message="the vLLM response envelope was not a JSON object",
        )
    return cast(dict[str, object], decoded)


def _choice_content(response: Mapping[str, object], *, max_chars: int) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        _invalid_output("the vLLM response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        _invalid_output("the vLLM choice was not an object")
    finish_reason = choice.get("finish_reason")
    if finish_reason not in {None, "stop"}:
        _invalid_output("the vLLM choice did not finish normally")
    message = choice.get("message")
    if not isinstance(message, dict):
        _invalid_output("the vLLM choice message was not an object")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        _invalid_output("the vLLM choice content was not a non-empty string")
    if len(content) > max_chars:
        _invalid_output("the vLLM structured content exceeded the configured character limit")
    return content


def _decode_structured_result(content: str) -> LLMTextExtractionResult:
    try:
        decoded = _decode_json(content)
        if not isinstance(decoded, dict):
            raise ValueError("structured content must be a JSON object")
        return LLMTextExtractionResult.model_validate(decoded)
    except (TypeError, ValueError):
        raise LLMInvalidStructuredOutputError(
            provider=_PROVIDER_NAME,
            message="the vLLM content did not satisfy the extraction JSON schema",
        ) from None


def _usage(response: Mapping[str, object]) -> tuple[int | None, int | None]:
    usage = response.get("usage")
    if usage is None:
        return None, None
    if not isinstance(usage, dict):
        _invalid_output("the vLLM usage value was not an object")
    return (
        _optional_non_negative_int(usage.get("prompt_tokens"), "prompt_tokens"),
        _optional_non_negative_int(usage.get("completion_tokens"), "completion_tokens"),
    )


def _optional_non_negative_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _invalid_output(f"the vLLM {name} value was invalid")
    return value


def _optional_request_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        _invalid_output("the vLLM request identifier was invalid")
    return value.strip()


def _header_request_id(headers: Mapping[str, str]) -> str | None:
    value = headers.get("x-request-id") or headers.get("X-Request-ID")
    return _optional_request_id(value)


def _invalid_output(message: str) -> NoReturn:
    raise LLMInvalidStructuredOutputError(provider=_PROVIDER_NAME, message=message)
