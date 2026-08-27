"""Network-free deterministic external Action Intent simulation."""

from app.platform.case_resolution import (
    ExternalActionIntent,
    ExternalActionMode,
    SimulationAdapterResult,
    SimulationOutcome,
)


class DeterministicDryRunExternalActionAdapter:
    """Validate an immutable intent without performing any external side effect."""

    def simulate(self, intent: ExternalActionIntent) -> SimulationAdapterResult:
        return self.execute(intent, mode=ExternalActionMode.DRY_RUN)

    def execute(
        self,
        intent: ExternalActionIntent,
        *,
        mode: ExternalActionMode,
    ) -> SimulationAdapterResult:
        request: dict[str, object] = {
            "intent_id": intent.id,
            "action_type": intent.action_type.value,
            "mode": mode.value,
            "order_ref": intent.order_ref,
            "product_ref": intent.product_ref,
            "amount": intent.amount,
            "currency": intent.currency,
            "quantity": intent.quantity,
            "shipping_address_ref": intent.shipping_address_ref,
        }
        if mode is ExternalActionMode.LIVE:
            return SimulationAdapterResult(
                outcome=SimulationOutcome.FAILED,
                mode=mode,
                side_effects_performed=False,
                failure_code="LIVE_EXTERNAL_ACTION_DISABLED",
                failure_message="LIVE external Action execution is disabled in Sprint 5C.",
                simulated_request=request,
                simulated_response={"accepted": False, "executed": False},
            )
        return SimulationAdapterResult(
            outcome=SimulationOutcome.VALIDATED,
            mode=mode,
            side_effects_performed=False,
            simulated_request=request,
            simulated_response={
                "accepted": True,
                "executed": False,
                "validation": "DETERMINISTIC_DRY_RUN_VALID",
            },
        )


__all__ = ["DeterministicDryRunExternalActionAdapter"]
