# ADR-0098: Synthetic commerce context is display-only and separate from Action input

- Status: Accepted
- Date: 2026-08-28

## Context

The internal PoC needs realistic customer, order, payment, delivery, and refund-document fields.
Those fields must not weaken ADR-0091 by becoming another source of External Action parameters, and
fictional contact data must not be mistaken for approved real customer PII.

## Decision

- PoC Case attributes may contain a reserved `synthetic_commerce_context` object with schema
  `synthetic_commerce_context/1.0.0` and classification `SYNTHETIC_DEMO_ONLY`.
- The object stores one immutable-at-report-time customer/order/delivery snapshot in the existing
  Case JSONB. Names are fictional; phone, payment method, and tracking values are masked; addresses
  retain an explicit `데모` or `가상` marker.
- The Case input validator rejects unknown fields, unmasked contact/payment/tracking values,
  inconsistent payment totals, naive timestamps, and unsupported classifications in the reserved
  object.
- A terminal `review_report/1.0.0` allowlists and content-hashes the validated synthetic snapshot.
  Invalid persisted context is omitted instead of copied into the report.
- Commerce amounts are display and reconciliation context only. Refund amount and currency continue
  to come exclusively from `attributes.external_action_input`; they are never inferred from
  `paid_amount`, unit price, discounts, customer text, or the product catalog.

## Consequences

- The console and printable refund confirmation can look like an operations record while remaining
  visibly fictional and non-contactable.
- Existing Case, Resolution, Action Intent, and Review Report database schemas need no migration
  because the versioned value uses existing JSONB snapshot fields.
- Existing reports remain immutable and do not gain the new context retroactively. Only reports
  created after a Human Decision on an enriched Case contain it.
- Real customer PII, CRM synchronization, payment-provider data, retention approval, and LIVE action
  remain outside the internal-demo scope.

## Related decisions

- [ADR-0091](0091-explicit-external-action-inputs-only.md)
- [ADR-0092](0092-atomic-resolution-request-and-immutable-intent.md)
- [ADR-0094](0094-dry-run-only-external-action.md)
