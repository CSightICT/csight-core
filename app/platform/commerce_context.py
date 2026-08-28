"""Validated synthetic commerce snapshots for the internal PoC.

The snapshot is display and reporting context only.  It is deliberately separate
from ``external_action_input`` so no payment or shipping action parameter can be
inferred from order or customer data.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYNTHETIC_COMMERCE_CONTEXT_KEY = "synthetic_commerce_context"
SYNTHETIC_COMMERCE_SCHEMA_VERSION = "synthetic_commerce_context/1.0.0"
SYNTHETIC_COMMERCE_CLASSIFICATION = "SYNTHETIC_DEMO_ONLY"

_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class _Snapshot(BaseModel):
    model_config = _MODEL_CONFIG


class SyntheticCustomerSnapshot(_Snapshot):
    customer_id: str = Field(pattern=r"^CUST-DEMO-[0-9]{6}$")
    display_name: str = Field(min_length=2, max_length=60)
    phone_masked: str = Field(pattern=r"^010-\*{4}-[0-9]{4}$")
    membership_tier: Literal["BASIC", "SILVER", "GOLD", "VIP"]


class SyntheticOrderSnapshot(_Snapshot):
    sales_channel: str = Field(min_length=2, max_length=80)
    seller_name: str = Field(min_length=2, max_length=80)
    ordered_at: datetime
    product_display_name: str = Field(min_length=2, max_length=120)
    sku: str = Field(pattern=r"^CS-DEMO-[A-Z]{3}-[0-9]{3}$")
    quantity: int = Field(ge=1, le=1000)
    unit_price: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    merchandise_amount: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    shipping_fee: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    discount_amount: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    paid_amount: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    currency: Literal["KRW"]
    payment_method_masked: str = Field(min_length=6, max_length=80)
    payment_status: Literal["PAID"]

    @field_validator("ordered_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ordered_at must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("payment_method_masked")
    @classmethod
    def require_masked_payment_method(cls, value: str) -> str:
        if "****" not in value:
            raise ValueError("payment_method_masked must not expose a full account number")
        return value

    @model_validator(mode="after")
    def require_consistent_totals(self) -> Self:
        if self.unit_price * self.quantity != self.merchandise_amount:
            raise ValueError("merchandise_amount must equal unit_price multiplied by quantity")
        if self.merchandise_amount + self.shipping_fee - self.discount_amount != self.paid_amount:
            raise ValueError("paid_amount must match merchandise, shipping, and discount totals")
        return self


class SyntheticDeliverySnapshot(_Snapshot):
    shipping_address_ref: str = Field(pattern=r"^DEMO-V2-ADDR-[0-9]{3}$")
    recipient: str = Field(min_length=2, max_length=60)
    phone_masked: str = Field(pattern=r"^010-\*{4}-[0-9]{4}$")
    postal_code: str = Field(pattern=r"^[0-9]{5}$")
    address_line1: str = Field(min_length=8, max_length=120)
    address_line2: str = Field(min_length=1, max_length=120)
    carrier: str = Field(min_length=2, max_length=80)
    tracking_number_masked: str = Field(min_length=8, max_length=80)
    delivered_at: datetime

    @field_validator("address_line1")
    @classmethod
    def require_fictional_address_marker(cls, value: str) -> str:
        if "데모" not in value and "가상" not in value:
            raise ValueError("synthetic address must retain an explicit fictional marker")
        return value

    @field_validator("tracking_number_masked")
    @classmethod
    def require_masked_tracking_number(cls, value: str) -> str:
        if "****" not in value:
            raise ValueError("tracking_number_masked must not expose a full tracking number")
        return value

    @field_validator("delivered_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("delivered_at must be timezone-aware")
        return value.astimezone(UTC)


class SyntheticCommerceContext(_Snapshot):
    schema_version: Literal["synthetic_commerce_context/1.0.0"]
    data_classification: Literal["SYNTHETIC_DEMO_ONLY"]
    customer: SyntheticCustomerSnapshot
    order: SyntheticOrderSnapshot
    delivery: SyntheticDeliverySnapshot
    disclaimer: Literal["FICTIONAL_IDENTITIES_CONTACTS_ADDRESSES_AND_TRANSACTIONS"]

    @model_validator(mode="after")
    def require_order_before_delivery(self) -> Self:
        if self.delivery.delivered_at < self.order.ordered_at:
            raise ValueError("delivered_at cannot precede ordered_at")
        return self


def validate_synthetic_commerce_context(value: object) -> SyntheticCommerceContext:
    """Validate the reserved Case attribute without importing infrastructure."""

    return SyntheticCommerceContext.model_validate(value)


def synthetic_commerce_snapshot(
    attributes: Mapping[str, object],
) -> dict[str, object] | None:
    """Return an allowlisted, masked snapshot; invalid or absent data is omitted."""

    value = attributes.get(SYNTHETIC_COMMERCE_CONTEXT_KEY)
    if value is None:
        return None
    try:
        context = validate_synthetic_commerce_context(value)
    except ValueError:
        return None
    return context.model_dump(mode="json")


__all__ = [
    "SYNTHETIC_COMMERCE_CLASSIFICATION",
    "SYNTHETIC_COMMERCE_CONTEXT_KEY",
    "SYNTHETIC_COMMERCE_SCHEMA_VERSION",
    "SyntheticCommerceContext",
    "synthetic_commerce_snapshot",
    "validate_synthetic_commerce_context",
]
