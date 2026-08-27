"""Ports for Case Resolution persistence and side-effect-free simulations."""

from __future__ import annotations

from typing import Protocol

from app.platform.case_resolution import (
    CaseResolution,
    CaseResolutionEvent,
    ExternalActionIntent,
    ExternalActionIntentDetail,
    SimulationAdapterResult,
    SimulationClaim,
)


class CaseResolutionReader(Protocol):
    def get_resolution(self, *, tenant_id: str, case_id: str) -> CaseResolution | None: ...

    def list_events(self, *, tenant_id: str, case_id: str) -> tuple[CaseResolutionEvent, ...]: ...

    def list_intents(self, *, tenant_id: str, case_id: str) -> tuple[ExternalActionIntent, ...]: ...

    def get_intent(
        self, *, tenant_id: str, intent_id: str
    ) -> ExternalActionIntentDetail | None: ...


class CaseResolutionRepository(CaseResolutionReader, Protocol):
    def process_requested(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        resolution_id: str,
        correlation_id: str,
    ) -> str: ...

    def record_resolution_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
    ) -> None: ...

    def prepare_simulation(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        external_action_intent_id: str,
        correlation_id: str,
    ) -> SimulationClaim | None: ...

    def complete_simulation(
        self,
        *,
        claim: SimulationClaim,
        result: SimulationAdapterResult,
    ) -> str: ...

    def record_simulation_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
        expected_execution_token: str | None = None,
    ) -> None: ...


class ExternalActionSimulationAdapter(Protocol):
    def simulate(self, intent: ExternalActionIntent) -> SimulationAdapterResult: ...


__all__ = [
    "CaseResolutionReader",
    "CaseResolutionRepository",
    "ExternalActionSimulationAdapter",
]
