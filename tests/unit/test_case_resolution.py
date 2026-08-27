"""Pure Sprint 5C mapping and network-free adapter contracts."""

from datetime import UTC, datetime

import pytest

from app.adapters.external_action import DeterministicDryRunExternalActionAdapter
from app.platform.case_resolution import (
    ExternalActionIntent,
    ExternalActionMode,
    ExternalActionType,
    ResolutionStatus,
    SimulationOutcome,
    assess_action_input,
)
from app.platform.human_review import HumanDecisionType

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("decision", "external_input", "expected_action", "expected_values"),
    [
        (
            HumanDecisionType.APPROVE_REFUND,
            {"amount": "15000.2500", "currency": "KRW"},
            ExternalActionType.REFUND,
            {"order_ref", "amount", "currency"},
        ),
        (
            HumanDecisionType.APPROVE_EXCHANGE,
            {"quantity": 1, "shipping_address_ref": "address-1"},
            ExternalActionType.EXCHANGE,
            {"order_ref", "product_ref", "quantity", "shipping_address_ref"},
        ),
        (
            HumanDecisionType.APPROVE_RESHIPMENT,
            {"quantity": 2, "shipping_address_ref": "address-2"},
            ExternalActionType.RESHIPMENT,
            {"order_ref", "product_ref", "quantity", "shipping_address_ref"},
        ),
        (
            HumanDecisionType.APPROVE_REPAIR,
            {"quantity": 1},
            ExternalActionType.REPAIR,
            {"order_ref", "product_ref", "quantity"},
        ),
    ],
)
def test_approval_mapping_uses_only_the_exact_explicit_input_matrix(
    decision: HumanDecisionType,
    external_input: dict[str, object],
    expected_action: ExternalActionType,
    expected_values: set[str],
) -> None:
    result = assess_action_input(
        decision=decision,
        order_ref=" order-1 ",
        product_ref=" product-1 ",
        attributes={
            "external_action_input": external_input,
            "order_amount": 999999,
            "currency": "USD",
        },
    )

    assert result.action_type is expected_action
    assert result.terminal_status is None
    assert set(result.values) == expected_values
    assert result.values["order_ref"] == "order-1"


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (HumanDecisionType.REJECT_REQUEST, ResolutionStatus.ACTION_NOT_REQUIRED),
        (HumanDecisionType.NO_ACTION, ResolutionStatus.ACTION_NOT_REQUIRED),
        (
            HumanDecisionType.PROVIDE_INFORMATION,
            ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
        ),
    ],
)
def test_non_approval_mapping_never_creates_an_action(
    decision: HumanDecisionType, expected_status: ResolutionStatus
) -> None:
    result = assess_action_input(
        decision=decision,
        order_ref="order-1",
        product_ref="product-1",
        attributes={"external_action_input": {"amount": "10", "currency": "KRW"}},
    )
    assert result.action_type is None
    assert result.terminal_status is expected_status
    assert result.values == {}


@pytest.mark.parametrize(
    "external_input",
    [
        {},
        {"amount": 10, "currency": "KRW"},
        {"amount": "10.00001", "currency": "KRW"},
        {"amount": "10", "currency": "krw"},
        {"amount": "10", "currency": "KRW", "quantity": 1},
        {"amount": "10", "currency": "KRW", "recipient": {"id": "nested"}},
    ],
)
def test_missing_invalid_irrelevant_or_nested_input_fails_closed(
    external_input: dict[str, object],
) -> None:
    result = assess_action_input(
        decision=HumanDecisionType.APPROVE_REFUND,
        order_ref="order-1",
        product_ref="product-1",
        attributes={"external_action_input": external_input},
    )
    assert result.terminal_status is ResolutionStatus.ACTION_NEEDS_INPUT
    assert result.missing_fields or result.invalid_fields


def test_amount_uses_fixed_point_and_counts_significant_digits_not_leading_zeroes() -> None:
    accepted = assess_action_input(
        decision=HumanDecisionType.APPROVE_REFUND,
        order_ref="order-1",
        product_ref=None,
        attributes={"external_action_input": {"amount": "0.0001", "currency": "KRW"}},
    )
    exponential = assess_action_input(
        decision=HumanDecisionType.APPROVE_REFUND,
        order_ref="order-1",
        product_ref=None,
        attributes={"external_action_input": {"amount": "1e3", "currency": "KRW"}},
    )
    too_precise = assess_action_input(
        decision=HumanDecisionType.APPROVE_REFUND,
        order_ref="order-1",
        product_ref=None,
        attributes={
            "external_action_input": {
                "amount": "123456789012345.67890",
                "currency": "KRW",
            }
        },
    )

    assert accepted.terminal_status is None
    assert accepted.values["amount"] == "0.0001"
    assert exponential.terminal_status is ResolutionStatus.ACTION_NEEDS_INPUT
    assert exponential.invalid_fields == ("amount",)
    assert too_precise.terminal_status is ResolutionStatus.ACTION_NEEDS_INPUT
    assert too_precise.invalid_fields == ("amount",)


def test_dry_run_is_deterministic_and_live_is_always_disabled() -> None:
    intent = ExternalActionIntent(
        id="intent-1",
        tenant_id="tenant-1",
        case_id="case-1",
        resolution_id="resolution-1",
        human_decision_id="decision-1",
        action_type=ExternalActionType.REPAIR,
        order_ref="order-1",
        product_ref="product-1",
        quantity=1,
        content_hash="a" * 64,
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )
    adapter = DeterministicDryRunExternalActionAdapter()
    first = adapter.simulate(intent)
    second = adapter.simulate(intent)
    live = adapter.execute(intent, mode=ExternalActionMode.LIVE)

    assert first == second
    assert first.outcome is SimulationOutcome.VALIDATED
    assert first.side_effects_performed is False
    assert live.outcome is SimulationOutcome.FAILED
    assert live.failure_code == "LIVE_EXTERNAL_ACTION_DISABLED"
    assert live.side_effects_performed is False
