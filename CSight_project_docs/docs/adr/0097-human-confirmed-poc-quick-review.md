# ADR-0097: Human-confirmed PoC quick review may compose existing review actions

- Status: Accepted
- Date: 2026-08-28

## Decision

The consultant console may present `ALLOW` and `DENY` as a one-click PoC review surface when a
deterministic readiness gate is satisfied. The gate threshold is `0.70` and measures workflow
readiness, not model confidence or real-world accuracy:

- policy summary is `REQUIRES_HUMAN_REVIEW`: `0.35`;
- at least one immutable policy rule result is available: `0.25`;
- at least one immutable policy citation is available: `0.15`;
- qualification metadata is present: `0.10`; and
- policy eligibility maps to one approval Decision type: `0.15`.

Additional-evidence states, missing policy basis, insufficient readiness, and unauthorized
Admin-only tasks fail closed. `ALLOW` is enabled only when the immutable packet's
`MARK_REVIEW_ELIGIBILITY` effects map to exactly one approval Decision under the existing versioned
contract. `DENY` maps to `REJECT_REQUEST`. Customer prose, Vision score, LLM output, rationale, and
requested-action inference are not mapping sources.

The click remains an explicit action by the authenticated human. The Web client may compose the
existing CAS claim and resolve APIs, automatically select the first packet-contained policy rule
and citation as basis, record a fixed transparent rationale, poll the existing immutable Review
Report endpoint, and open the report when the asynchronous Resolution reaches a terminal state.

## Consequences

- No model, policy worker, outbox, or background task gains permission to create a Human Decision.
- The existing atomic Human Decision and Resolution-request transaction is unchanged.
- The existing deterministic Resolution, network-free `DRY_RUN`, and immutable
  `review_report/1.0.0` path performs the post-click work.
- A lost response or CAS conflict reloads current state; the client does not create a second
  Decision or replace an existing Decision.
- Detailed decision and additional-evidence controls remain available for cases that do not fit the
  quick-review gate.
- The `0.70` value is a product-demo usability threshold and must not be reported as calibrated
  accuracy, probability, risk, or a Limited-PoC qualification result.

## Related decisions

- [ADR-0077](0077-human-review-only-final-decision-source.md)
- [ADR-0084](0084-decision-basis-allowlist.md)
- [ADR-0090](0090-versioned-human-decision-action-mapping.md)
- [ADR-0094](0094-dry-run-only-external-action.md)
