# Policy Rule Schema v1

Rule sets pin schema, field-registry, operator-registry, and aggregation versions to `1.0.0` and
carry tenant, effective interval, source corpus identity/hash, and a stable content hash.

## Fields

| Type | Fields |
|---|---|
| Integer/number | `case.days_since_purchase`, `case.order_amount`, `evidence.available_image_count`, `extraction.claim_count` |
| String | `case.product_category`, `case.declared_requested_action`, `vision.qualification_status`, `alignment.status` |
| Boolean | `case.has_order_reference`, `case.has_product_reference` |
| String set | `completeness.system_missing_information`, `extraction.issue_types`, `vision.detected_defect_types` |

## Operators

Equality supports scalar typed values; ordering supports integer/number; `IN`/`NOT_IN` use typed
scalar lists; `CONTAINS*` supports string sets; `EXISTS`/`NOT_EXISTS` checks presence. Arbitrary
field paths, regex execution, Python expressions, SQL, JSONPath, and method calls are invalid.

Each rule has one or more conditions, effects, and source references. Allowed effects are
`MARK_REVIEW_ELIGIBILITY`, `REQUIRE_ADDITIONAL_EVIDENCE`, `REQUIRE_HUMAN_REVIEW`,
`REQUIRE_MANAGER_REVIEW`, `PROHIBIT_AUTOMATION`, and `FLAG_POLICY_EXCEPTION`. The schema cannot
represent final approval, rejection, fraud, or liability.
