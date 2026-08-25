"""Technology-neutral observability boundary for upload compensation failures."""

from typing import Literal, Protocol, runtime_checkable

CompensationStep = Literal["object_delete", "evidence_mark_failed"]


@runtime_checkable
class CompensationFailureObserver(Protocol):
    """Record only safe identifiers when a best-effort compensation step fails."""

    def record_failure(
        self,
        *,
        step: CompensationStep,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        error_type: str,
    ) -> None: ...
