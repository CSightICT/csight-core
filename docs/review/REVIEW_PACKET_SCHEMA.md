# Immutable Review Packet Schema

One packet is created per task and never updated. Its SHA-256 hash covers the immutable payload.

## References

- tenant, case, analysis run, and policy evaluation run
- rule-set ID, version, and content hash
- extraction v2/completeness result
- Vision result IDs and optional alignment result
- optional citation pack and grounded-explanation result
- all review-producing policy effects and evaluation summary

## Allowlisted case metadata

`days_since_purchase`, `order_amount`, `product_category`, `declared_requested_action`, order/product
reference presence, and available image count. Customer text is not copied.

## Qualification snapshot

LLM, Vision, alignment, and grounding scopes are frozen for reviewer display. Values such as
`LOCAL_POC`, `MOCK_QUALIFIED`, and `NOT_AVAILABLE` describe qualification, not factual certainty.

## Integrity gates

Tenant/case/run relationships, successful policy status, rule-set hash, source run identity,
citation/grounding relationship, and Vision run identity fail closed. Decision basis is later
resolved only against this packet's allowlist. New evidence after evidence request does not mutate
the packet; packet revision is deferred.
