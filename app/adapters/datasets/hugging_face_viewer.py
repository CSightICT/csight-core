"""Bounded Hugging Face Dataset Viewer adapter with replayable provenance."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, cast
from urllib.parse import urlencode

import urllib3
from urllib3 import Timeout
from urllib3.response import BaseHTTPResponse

from app.platform.quantization_assets import QuantizationAssetError, SourcePin
from app.platform.quantization_source_prep import (
    AttestedPublicDatasetRows,
    DatasetViewerPageAttestation,
    PublicDatasetFixtureAttestation,
    PublicDatasetRow,
    dataset_viewer_query_identity_digest,
    serialize_public_fixture,
    sha256_digest,
    validate_attested_public_rows,
    validate_public_source_pin,
)

_BASE_URL = "https://datasets-server.huggingface.co/rows"
_MAX_PAGE_SIZE = 100
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_MAX_CAPTURE_BYTES = 512 * 1024 * 1024


class _HTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        **urlopen_kw: Any,
    ) -> BaseHTTPResponse: ...


class HuggingFaceDatasetViewerRows:
    """Capture public rows and exact query/response evidence for offline replay."""

    def __init__(
        self,
        *,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        page_size: int = _MAX_PAGE_SIZE,
        http_client: _HTTPClient | None = None,
    ) -> None:
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("Dataset Viewer timeouts must be positive")
        if not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise ValueError("Dataset Viewer page size must be between 1 and 100")
        self._timeout = Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
        )
        self._page_size = page_size
        self._http_client = http_client or cast(_HTTPClient, urllib3.PoolManager())

    def iter_rows(
        self,
        *,
        source: SourcePin,
        maximum_rows: int,
    ) -> Iterable[PublicDatasetRow]:
        """Compatibility iterator; source preparation uses the attested batch method."""

        return iter(self.fetch_attested_rows(source=source, maximum_rows=maximum_rows).rows)

    def fetch_attested_rows(
        self,
        *,
        source: SourcePin,
        maximum_rows: int,
    ) -> AttestedPublicDatasetRows:
        validate_public_source_pin(source)
        if not 1 <= maximum_rows <= 50_000:
            raise ValueError("maximum_rows must be between 1 and 50000")
        offset = 0
        captured_rows: list[PublicDatasetRow] = []
        pages: list[DatasetViewerPageAttestation] = []
        captured_response_bytes = 0
        captured_fixture_bytes = 0
        while offset < maximum_rows:
            length = min(self._page_size, maximum_rows - offset)
            query = urlencode(
                {
                    "dataset": source.source_id,
                    "config": source.config,
                    "split": source.split,
                    "offset": offset,
                    "length": length,
                    "revision": source.revision,
                }
            )
            response = self._http_client.request(
                "GET",
                f"{_BASE_URL}?{query}",
                timeout=self._timeout,
                preload_content=True,
                redirect=False,
            )
            if response.status != 200:
                raise QuantizationAssetError(
                    f"Dataset Viewer returned HTTP {response.status} for a pinned source"
                )
            observed_revision = response.headers.get("x-revision")
            if not isinstance(observed_revision, str) or observed_revision != source.revision:
                raise QuantizationAssetError(
                    "Dataset Viewer did not attest the requested exact source revision"
                )
            data = bytes(response.data or b"")
            if len(data) > _MAX_RESPONSE_BYTES:
                raise QuantizationAssetError("Dataset Viewer response exceeds the size limit")
            payload = _decode_page(data)
            if payload.get("partial") not in (None, False):
                raise QuantizationAssetError(
                    "Dataset Viewer returned a partial response; full provenance is required"
                )
            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise QuantizationAssetError("Dataset Viewer response is missing rows")
            if len(rows) > length:
                raise QuantizationAssetError(
                    "Dataset Viewer returned more rows than the exact page query requested"
                )
            page_rows: list[PublicDatasetRow] = []
            for wrapper in rows:
                if not isinstance(wrapper, Mapping):
                    raise QuantizationAssetError("Dataset Viewer row wrapper is invalid")
                row_index = wrapper.get("row_idx")
                values = wrapper.get("row")
                truncated_cells = wrapper.get("truncated_cells", [])
                if not isinstance(row_index, int) or not isinstance(values, Mapping):
                    raise QuantizationAssetError("Dataset Viewer row payload is invalid")
                if not isinstance(truncated_cells, list) or truncated_cells:
                    raise QuantizationAssetError(
                        "Dataset Viewer returned a truncated row; full provenance is required"
                    )
                if row_index != offset + len(page_rows):
                    raise QuantizationAssetError(
                        "Dataset Viewer row index does not match the requested page"
                    )
                page_rows.append(PublicDatasetRow(row_index=row_index, values=dict(values)))
            yielded = len(page_rows)
            canonical_page = serialize_public_fixture(page_rows)
            captured_response_bytes += len(data)
            captured_fixture_bytes += len(canonical_page)
            if (
                captured_response_bytes > _MAX_CAPTURE_BYTES
                or captured_fixture_bytes > _MAX_CAPTURE_BYTES
            ):
                raise QuantizationAssetError(
                    "Dataset Viewer capture exceeds the aggregate size limit"
                )
            pages.append(
                DatasetViewerPageAttestation(
                    offset=offset,
                    length=length,
                    row_count=yielded,
                    response_revision=observed_revision,
                    response_body_digest=sha256_digest(data),
                    response_body_bytes=len(data),
                    canonical_rows_digest=sha256_digest(canonical_page),
                    canonical_rows_bytes=len(canonical_page),
                )
            )
            captured_rows.extend(page_rows)
            if yielded == 0 or yielded < length:
                break
            offset += yielded

        config = source.config
        split = source.split
        if config is None or split is None:
            raise QuantizationAssetError("public Dataset Viewer source lacks config or split")
        fixture_payload = serialize_public_fixture(captured_rows)
        query_identity_digest = dataset_viewer_query_identity_digest(
            source_id=source.source_id,
            source_revision=source.revision,
            config=config,
            split=split,
            requested_maximum_rows=maximum_rows,
            page_size=self._page_size,
            pages=pages,
        )
        result = AttestedPublicDatasetRows(
            rows=tuple(captured_rows),
            attestation=PublicDatasetFixtureAttestation(
                source_id=source.source_id,
                source_revision=source.revision,
                config=config,
                split=split,
                requested_maximum_rows=maximum_rows,
                page_size=self._page_size,
                fixture_payload_digest=sha256_digest(fixture_payload),
                fixture_payload_bytes=len(fixture_payload),
                fixture_row_count=len(captured_rows),
                query_identity_digest=query_identity_digest,
                pages=tuple(pages),
            ),
        )
        validate_attested_public_rows(
            source=source,
            attested_rows=result,
            maximum_rows=maximum_rows,
        )
        return result


def _decode_page(data: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QuantizationAssetError("Dataset Viewer returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise QuantizationAssetError("Dataset Viewer response must be a JSON object")
    return value


__all__ = ["HuggingFaceDatasetViewerRows"]
