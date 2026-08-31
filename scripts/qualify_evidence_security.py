"""Exercise the real HTTP Evidence path against a live ClamAV service."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import secrets
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class QualificationStepError(RuntimeError):
    """Sanitized stage marker for qualification diagnostics."""

    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause_type = type(cause).__name__
        super().__init__("qualification step failed")


@contextmanager
def _stage(name: str) -> Generator[None, None, None]:
    try:
        yield
    except (OSError, RuntimeError, ValueError) as error:
        raise QualificationStepError(name, error) from error


def _request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return (
                response.status,
                response.read(),
                {name.lower(): value for name, value in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.read(),
            {name.lower(): value for name, value in error.headers.items()},
        )


def _json_request(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    body = None if data is None else json.dumps(data).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    status, response, _ = _request(
        url,
        method=method,
        body=body,
        headers=request_headers,
    )
    try:
        payload = json.loads(response)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    return status, payload


def _multipart_image(
    *,
    content: bytes,
    filename: str,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"csight-{secrets.token_hex(16)}"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="evidence_type"\r\n\r\n'
        "IMAGE\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("ascii")
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    return prefix + content + suffix, f"multipart/form-data; boundary={boundary}"


def _jpeg_with_private_exif() -> bytes:
    image = Image.new("RGB", (8, 5), "navy")
    metadata = image.getexif()
    metadata[0x010E] = "qualification-private-description"
    metadata[0x0112] = 6
    output = BytesIO()
    image.save(output, format="JPEG", exif=metadata)
    image.close()
    return output.getvalue()


def _error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _upload(
    *,
    api_base: str,
    case_id: str,
    token: str,
    content: bytes,
    filename: str,
    idempotency_key: str,
) -> tuple[int, Any]:
    body, content_type = _multipart_image(
        content=content,
        filename=filename,
        content_type="image/jpeg",
    )
    status, raw, _ = _request(
        f"{api_base}/api/v1/cases/{case_id}/evidence",
        method="POST",
        body=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Idempotency-Key": idempotency_key,
        },
    )
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    return status, payload


def _probe_declared_oversized_request(
    *,
    api_base: str,
    case_id: str,
    token: str,
) -> tuple[int, Any]:
    parsed = urlsplit(api_base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("qualification API must be loopback HTTP")
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=20)
    try:
        connection.putrequest("POST", f"/api/v1/cases/{case_id}/evidence")
        connection.putheader("Accept", "application/json")
        connection.putheader("Authorization", f"Bearer {token}")
        connection.putheader("Content-Type", "multipart/form-data; boundary=declared-oversized")
        connection.putheader("Content-Length", str(3 * 1024 * 1024))
        connection.putheader("Idempotency-Key", "evidence-security-oversized-v1")
        connection.endheaders()
        response = connection.getresponse()
        raw = response.read()
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        return response.status, payload
    finally:
        connection.close()


def _authenticate(api_base: str, password: str) -> str:
    status, payload = _json_request(
        f"{api_base}/api/v1/auth/token",
        method="POST",
        data={
            "tenant_slug": "csight-demo",
            "email": "admin@csight.demo",
            "password": password,
        },
    )
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError("qualification authentication failed")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("qualification authentication returned no token")
    return token


def _create_case(api_base: str, token: str) -> str:
    status, payload = _json_request(
        f"{api_base}/api/v1/cases",
        method="POST",
        data={
            "order_ref": "EVIDENCE-QUALIFICATION-ORDER",
            "product_ref": "EVIDENCE-QUALIFICATION-SKU",
            "customer_message": "Synthetic evidence security qualification case.",
            "requested_action": "UNSPECIFIED",
            "attributes": {},
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "evidence-security-qualification-case-v1",
        },
    )
    if status not in {200, 201} or not isinstance(payload, dict):
        raise RuntimeError("qualification Case creation failed")
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise RuntimeError("qualification Case response has no ID")
    return case_id


def _healthy_phase(api_base: str, password: str) -> dict[str, bool | str]:
    with _stage("authenticate"):
        token = _authenticate(api_base, password)
    with _stage("create_case"):
        case_id = _create_case(api_base, token)
    original = _jpeg_with_private_exif()
    with _stage("clean_upload"):
        clean_status, clean_payload = _upload(
            api_base=api_base,
            case_id=case_id,
            token=token,
            content=original,
            filename="clean-with-exif.jpg",
            idempotency_key="evidence-security-clean-v1",
        )
    evidence_id = clean_payload.get("evidence_id") if isinstance(clean_payload, dict) else None
    clean_stored = clean_status == 201 and isinstance(evidence_id, str)

    metadata_removed = False
    raw_changed = False
    if clean_stored:
        with _stage("clean_readback"):
            status, stored, headers = _request(
                f"{api_base}/api/v1/cases/{case_id}/evidence/{evidence_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )
        if status == 200 and headers.get("content-type", "").startswith("image/jpeg"):
            raw_changed = stored != original
            with Image.open(BytesIO(stored)) as image:
                metadata_removed = (
                    image.size == (5, 8)
                    and len(image.getexif()) == 0
                    and b"qualification-private-description" not in stored
                )

    with _stage("eicar_upload"):
        malware_status, malware_payload = _upload(
            api_base=api_base,
            case_id=case_id,
            token=token,
            content=_EICAR,
            filename="eicar.jpg",
            idempotency_key="evidence-security-eicar-v1",
        )
    with _stage("malformed_upload"):
        malformed_status, malformed_payload = _upload(
            api_base=api_base,
            case_id=case_id,
            token=token,
            content=b"not-an-image",
            filename="malformed.jpg",
            idempotency_key="evidence-security-malformed-v1",
        )
    with _stage("oversized_upload"):
        oversized_status, oversized_payload = _probe_declared_oversized_request(
            api_base=api_base,
            case_id=case_id,
            token=token,
        )

    results: dict[str, bool | str] = {
        "qualification": "live-clamav-evidence-http",
        "clean_http_status": str(clean_status),
        "clean_error_code": _error_code(clean_payload) or "NONE",
        "clean_image_stored": clean_stored,
        "original_bytes_reencoded": raw_changed,
        "exif_removed_and_orientation_applied": metadata_removed,
        "eicar_rejected_before_image_decode": (
            malware_status == 422 and _error_code(malware_payload) == "UNSAFE_EVIDENCE"
        ),
        "eicar_http_status": str(malware_status),
        "eicar_error_code": _error_code(malware_payload) or "NONE",
        "malformed_image_rejected": (
            malformed_status == 422 and _error_code(malformed_payload) == "INVALID_IMAGE_CONTENT"
        ),
        "malformed_http_status": str(malformed_status),
        "malformed_error_code": _error_code(malformed_payload) or "NONE",
        "oversized_request_rejected": (
            oversized_status == 413 and _error_code(oversized_payload) == "FILE_TOO_LARGE"
        ),
    }
    gate_names = {
        "clean_image_stored",
        "original_bytes_reencoded",
        "exif_removed_and_orientation_applied",
        "eicar_rejected_before_image_decode",
        "malformed_image_rejected",
        "oversized_request_rejected",
    }
    failed = [name for name, value in results.items() if name in gate_names and value is not True]
    results["verdict"] = "PASS" if not failed else "BLOCKED"
    results["failed_gates"] = ",".join(failed)
    return results


def _outage_phase(api_base: str, password: str) -> dict[str, bool | str]:
    with _stage("outage_authenticate"):
        token = _authenticate(api_base, password)
    with _stage("outage_create_case"):
        case_id = _create_case(api_base, token)
    with _stage("outage_upload"):
        status, payload = _upload(
            api_base=api_base,
            case_id=case_id,
            token=token,
            content=_jpeg_with_private_exif(),
            filename="scanner-outage.jpg",
            idempotency_key="evidence-security-outage-v1",
        )
    unavailable = status == 503 and _error_code(payload) == "EVIDENCE_SECURITY_UNAVAILABLE"
    return {
        "qualification": "live-clamav-outage-http",
        "scanner_outage_fails_closed": unavailable,
        "verdict": "PASS" if unavailable else "BLOCKED",
        "failed_gates": "" if unavailable else "scanner_outage_fails_closed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("healthy", "outage"), required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:18100")
    arguments = parser.parse_args()
    password = os.environ.get("EVIDENCE_QUALIFICATION_ADMIN_PASSWORD", "")
    if len(password) < 12:
        print(json.dumps({"verdict": "ERROR", "reason": "missing qualification password"}))
        return 1
    try:
        results = (
            _healthy_phase(arguments.api_base, password)
            if arguments.phase == "healthy"
            else _outage_phase(arguments.api_base, password)
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "verdict": "ERROR",
                    "phase": getattr(error, "stage", arguments.phase),
                    "error_type": getattr(error, "cause_type", type(error).__name__),
                    "reason": "qualification execution failed",
                }
            )
        )
        return 1
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if results["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
