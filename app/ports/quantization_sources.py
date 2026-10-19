"""Port for attested public rows used by explicit quantization source preparation."""

from typing import Protocol

from app.platform.quantization_assets import SourcePin
from app.platform.quantization_source_prep import AttestedPublicDatasetRows


class PublicDatasetRowsPort(Protocol):
    """Capture bounded rows and provenance from one exact public dataset source."""

    def fetch_attested_rows(
        self,
        *,
        source: SourcePin,
        maximum_rows: int,
    ) -> AttestedPublicDatasetRows: ...


__all__ = ["PublicDatasetRowsPort"]
