"""Service container and app-state provider for operations reads."""

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.application.demo_reset import DemoReset
from app.application.model_activation import (
    ActivateSignedModelRelease,
    GetActiveModelRelease,
    RegisterSignedModelRelease,
)
from app.application.model_routing import ActivateModelRoutePlan, GetActiveModelRoutePlan
from app.application.onboarding_readiness import GetOnboardingReadiness
from app.application.operations import (
    CancelOperationalFailure,
    GetOperationsFailures,
    GetOperationsOverview,
    ListOperationalFailures,
    ReplayOperationalFailure,
)
from app.application.pilot_readiness import GetPilotReadiness


@dataclass(frozen=True, slots=True)
class OperationsServiceContainer:
    get_overview: GetOperationsOverview
    get_failures: GetOperationsFailures
    list_failure_records: ListOperationalFailures | None = None
    replay_failure: ReplayOperationalFailure | None = None
    cancel_failure: CancelOperationalFailure | None = None
    register_model_release: RegisterSignedModelRelease | None = None
    activate_model_release: ActivateSignedModelRelease | None = None
    get_active_model_release: GetActiveModelRelease | None = None
    activate_model_route: ActivateModelRoutePlan | None = None
    get_active_model_route: GetActiveModelRoutePlan | None = None
    get_onboarding_readiness: GetOnboardingReadiness | None = None
    get_pilot_readiness: GetPilotReadiness | None = None
    demo_reset: DemoReset | None = None


def provide_operations_services(request: Request) -> OperationsServiceContainer | None:
    configured_services = getattr(request.app.state, "operations_services", None)
    if configured_services is None:
        return None
    return cast(OperationsServiceContainer, configured_services)


__all__ = ["OperationsServiceContainer", "provide_operations_services"]
