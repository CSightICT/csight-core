# External Action Contract

- Status: Accepted Sprint 5C design
- Date: 2026-08-27
- Mapping contract: `human_decision_to_external_action/1.0.0`
- Intent schema: `external_action_intent/1.0.0`
- Simulation result schema: `external_action_simulation_result/1.0.0`
- Implementation status: Implemented for deterministic `DRY_RUN`; this is not real-provider or
  real-business-action qualification evidence.

## Decision mapping

The mapping is deterministic and exhaustive for `human_decision/1.0.0`.

| Human Decision | `action_type` | `terminal_status` |
|---|---|---|
| `APPROVE_REFUND` | `REFUND` | None |
| `APPROVE_EXCHANGE` | `EXCHANGE` | None |
| `APPROVE_RESHIPMENT` | `RESHIPMENT` | None |
| `APPROVE_REPAIR` | `REPAIR` | None |
| `REJECT_REQUEST` | None | `ACTION_NOT_REQUIRED` |
| `NO_ACTION` | None | `ACTION_NOT_REQUIRED` |
| `PROVIDE_INFORMATION` | None | `MANUAL_FOLLOW_UP_REQUIRED` |

An unknown Decision type or contract version fails closed. Mapping does not inspect rationale,
policy text, model output, customer text, requested action, or order amount.

## Only permitted parameter sources

Action parameters may be read only from:

- `cases.order_ref`;
- `cases.product_ref`; and
- the explicitly submitted flat object `cases.attributes.external_action_input`.

The external input object has exactly four possible keys: `amount`, `currency`, `quantity`, and
`shipping_address_ref`. It must be a JSON object. Nested objects, arrays, unknown keys, or a known
key that is not applicable to the selected Action type are invalid.

Values are not copied from similarly named fields elsewhere. In particular, the resolver must not
infer or default amount, currency, quantity, or shipping address from `order_amount`, customer text,
LLM/Vision output, policy results, reviewer rationale, the Human Decision, or another Case.

## Strict field types

| Field | Strict input contract | Canonical form |
|---|---|---|
| `order_ref` | Non-blank Case field | Trimmed opaque string |
| `product_ref` | Non-blank Case field when required | Trimmed opaque string |
| `amount` | JSON string without surrounding whitespace, parsed as finite Decimal greater than zero, with at most 4 fractional digits, 15 integer digits, and 19 significant digits | Non-exponent fixed-point decimal string |
| `currency` | JSON string matching exactly `[A-Z]{3}` | Unchanged uppercase string |
| `quantity` | JSON integer from 1 through 1000; Boolean is rejected | Integer |
| `shipping_address_ref` | JSON string, trimmed length 1 through 255 | Trimmed opaque reference, never an address body |

No numeric-to-string, string-to-integer, case-folding, Boolean-to-integer, or nested-value coercion is
permitted. The currency rule validates format only; it does not infer currency or claim that every
three-letter value is supported by a live provider.

## Action-specific required matrix

| Action type | Case fields required | `external_action_input` fields required | Other external input fields |
|---|---|---|---|
| `REFUND` | `order_ref` | `amount`, `currency` | Rejected |
| `EXCHANGE` | `order_ref`, `product_ref` | `quantity`, `shipping_address_ref` | Rejected |
| `RESHIPMENT` | `order_ref`, `product_ref` | `quantity`, `shipping_address_ref` | Rejected |
| `REPAIR` | `order_ref`, `product_ref` | `quantity` | Rejected |

Missing and invalid fields are reported deterministically as sorted field-name lists. Either result
sets Resolution to `ACTION_NEEDS_INPUT` and creates no Action Intent, adapter command, Simulation
Attempt, or Simulation Result. Sprint 5C provides no input-completion endpoint.

## Immutable Action Intent

Only a complete actionable mapping may create an Intent. The typed record contains at least:

- Intent, Tenant, Case, Resolution, and Human Decision IDs;
- `action_type` and fixed `mode = DRY_RUN`;
- only the fields permitted by the action-specific matrix;
- mapping and intent-schema versions;
- canonical Intent content hash; and
- creation timestamp.

The hash covers the schema version, identity links, action type, mode, normalized parameters, and
mapping version using canonical JSON and SHA-256. The repository exposes add/get operations only.
There is no update, delete, replace, or generic untyped payload path.

## Simulation contract

The Sprint 5C adapter is a pure, deterministic, network-free validator. Given the same valid Intent
and simulator version, it produces the same normalized request, response, and outcome. Persisted
Result hashes also cover the unique Result identity and timestamp, so separate Result records are
not expected to share a hash.

| Mode | Outcome | Required safety value |
|---|---|---|
| `DRY_RUN` | `VALIDATED` or typed `FAILED` | `side_effects_performed = false` |
| `LIVE` | `FAILED` with `LIVE_EXTERNAL_ACTION_DISABLED` | `side_effects_performed = false` |

The Resolution worker emits only `DRY_RUN` Intents. The adapter still handles `LIVE` defensively and
fails before any provider or network call. No successful simulation means that a refund, exchange,
reshipment, or repair occurred; it means only that the immutable command shape passed local checks.

Attempt rows are never deleted and their fenced lifecycle status is completed in place; Results are
immutable and content-hashed. Duplicate delivery of the exact simulation event creates no duplicate
committed Result. Intent hash mismatch fails with `CASE_RESOLUTION_INTEGRITY_FAILED`; unknown schema,
action, or mode also fails closed. Every Result, including every failure, records
`side_effects_performed = false`.

## Public representation

Read APIs may expose normalized Action fields, schema and mapping versions, outcome, safe failure
code, timestamps, and content hashes. They must not expose dispatcher claims, leases, raw queue
payloads, credentials, full shipping addresses, customer text, reviewer rationale, or provider
secrets. `shipping_address_ref` remains an opaque reference.

## Related accepted decisions

- [ADR-0090](../../CSight_project_docs/docs/adr/0090-versioned-human-decision-action-mapping.md)
- [ADR-0091](../../CSight_project_docs/docs/adr/0091-explicit-external-action-inputs-only.md)
- [ADR-0092](../../CSight_project_docs/docs/adr/0092-atomic-resolution-request-and-immutable-intent.md)
- [ADR-0094](../../CSight_project_docs/docs/adr/0094-dry-run-only-external-action.md)
