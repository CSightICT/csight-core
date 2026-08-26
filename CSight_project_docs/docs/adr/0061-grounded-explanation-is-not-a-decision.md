# ADR-0061: Grounded policy explanation is not a business decision

- Status: Accepted
- Date: 2026-08-27

## Decision

The grounded output contains a fixed neutral summary, cited policy statements, and unresolved
evidence conditions only. Approval, rejection, refund, exchange, fraud, seller/delivery
responsibility, liability, applicability, and final-decision fields are absent and rejected as extra
fields.

## Consequences

The explanation remains evidence support for a future versioned Policy Engine and Human Review; it
cannot authorize or route customer outcomes.
