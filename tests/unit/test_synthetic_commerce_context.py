from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest
from pydantic import ValidationError

from app.platform.case.models import JsonValue, validate_json_object
from app.platform.commerce_context import synthetic_commerce_snapshot


def _context() -> dict[str, object]:
    return {
        "schema_version": "synthetic_commerce_context/1.0.0",
        "data_classification": "SYNTHETIC_DEMO_ONLY",
        "customer": {
            "customer_id": "CUST-DEMO-100002",
            "display_name": "김하늘",
            "phone_masked": "010-****-4821",
            "membership_tier": "GOLD",
        },
        "order": {
            "sales_channel": "CSight 마켓",
            "seller_name": "CSight 리빙",
            "ordered_at": "2026-08-25T10:14:00+09:00",
            "product_display_name": "화이트랩 바디 로션 300",
            "sku": "CS-DEMO-FLP-002",
            "quantity": 1,
            "unit_price": "18900",
            "merchandise_amount": "18900",
            "shipping_fee": "0",
            "discount_amount": "0",
            "paid_amount": "18900",
            "currency": "KRW",
            "payment_method_masked": "신한카드 **** 1042",
            "payment_status": "PAID",
        },
        "delivery": {
            "shipping_address_ref": "DEMO-V2-ADDR-002",
            "recipient": "김하늘",
            "phone_masked": "010-****-4821",
            "postal_code": "06236",
            "address_line1": "서울특별시 데모구 시연로 28",
            "address_line2": "CSight 타워 101호",
            "carrier": "CSight 로지스",
            "tracking_number_masked": "CSL-****-0202",
            "delivered_at": "2026-08-27T14:22:00+09:00",
        },
        "disclaimer": "FICTIONAL_IDENTITIES_CONTACTS_ADDRESSES_AND_TRANSACTIONS",
    }


@pytest.mark.unit
def test_reserved_commerce_context_is_validated_and_snapshotted() -> None:
    attributes = validate_json_object({"synthetic_commerce_context": cast(JsonValue, _context())})
    snapshot = synthetic_commerce_snapshot(attributes)

    assert snapshot is not None
    assert snapshot["data_classification"] == "SYNTHETIC_DEMO_ONLY"
    assert snapshot["customer"]["phone_masked"] == "010-****-4821"  # type: ignore[index]
    assert snapshot["order"]["paid_amount"] == "18900"  # type: ignore[index]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("customer", "phone_masked"), "010-1234-4821", "phone_masked"),
        (("delivery", "address_line1"), "서울특별시 강남구 테헤란로 1", "fictional marker"),
        (("order", "payment_method_masked"), "신한카드 1234 5678", "must not expose"),
        (("order", "paid_amount"), "19900", "paid_amount must match"),
    ],
)
def test_reserved_commerce_context_rejects_unmasked_or_inconsistent_values(
    path: tuple[str, str], value: str, match: str
) -> None:
    context = deepcopy(_context())
    parent = context[path[0]]
    assert isinstance(parent, dict)
    parent[path[1]] = value

    with pytest.raises(ValidationError, match=match):
        validate_json_object({"synthetic_commerce_context": cast(JsonValue, context)})


@pytest.mark.unit
def test_invalid_persisted_context_is_omitted_instead_of_leaking_raw_values() -> None:
    context = _context()
    customer = context["customer"]
    assert isinstance(customer, dict)
    customer["phone_masked"] = "010-1234-4821"

    assert synthetic_commerce_snapshot({"synthetic_commerce_context": context}) is None
