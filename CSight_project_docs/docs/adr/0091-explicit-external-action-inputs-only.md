# ADR-0091: External Action parameters are explicit and never inferred

- Status: Accepted
- Date: 2026-08-27

## Decision

Action parameters may come only from Case `order_ref`, Case `product_ref`, and the flat, strictly
typed `attributes.external_action_input` allowlist. Required fields are action-specific. Unknown,
nested, missing, invalid, coerced, or action-irrelevant values fail closed at `ACTION_NEEDS_INPUT`.

## Consequences

Amount, currency, quantity, and shipping reference are never derived from order amount, LLM/Vision
output, policy text, customer text, rationale, or defaults. Incomplete input creates no Intent,
adapter command, Attempt, or Result, and Sprint 5C adds no input-completion API.
