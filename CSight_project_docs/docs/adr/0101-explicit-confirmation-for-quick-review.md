# ADR-0101: Quick review requires an explicit confirmation step

- Status: Accepted
- Date: 2026-08-29
- Supersedes: the one-click interaction described by ADR-0097

## Context

ADR-0097 allowed a single authenticated click to compose claim and resolve operations when a
deterministic readiness gate passed. That preserved human authority, but it did not provide enough
protection against an accidental click, an incompletely loaded evidence image, or an operator who
had not yet seen the exact Decision and rationale that would become immutable.

## Decision

The first `ALLOW` or `DENY` interaction opens a confirmation surface and performs no mutation. The
surface shows the inquiry and order summary, every evidence loading or failure state, the selected
policy basis, model qualification state, and the exact Decision and rationale to be recorded.

Case metadata must load successfully and every `IMAGE` evidence item must both return authenticated
same-origin bytes and emit a successful browser decode event before either quick confirmation or
the manual Decision form is enabled. Loading, fetch failure, unavailable upload, and decode failure
all fail closed; an actually empty evidence list remains a distinct reviewable state. Retry creates
a fresh check, and the summary and confirmation surfaces keep separate decode state so one mounted
preview cannot incorrectly unlock another. No silent override is added.

Only a second explicit confirmation by the authenticated operator may compose the existing claim
and resolve APIs. Cancel, Escape, browser navigation, and dialog dismissal create zero Decisions.
The confirmation operation retains one idempotent intent until the client has observed its result.
After a `409` or a lost response, the client re-reads the current task and Decision before offering
another mutation. An existing Decision is shown with its correlation identifier and is never
replaced by the quick-review client.

## Consequences

- Human Review remains the only source of a final Decision.
- The atomic server-side Decision and Resolution-request transaction is unchanged.
- Accessibility semantics, focus trapping/restoration, keyboard dismissal, and a minimum 44-pixel
  target are part of the confirmation contract rather than optional styling.
- Model or policy readiness can enable the confirmation choice but cannot skip confirmation.
- ADR-0097 remains applicable to readiness and deterministic mapping; its one-click interaction is
  no longer accepted.

## Related decisions

- [ADR-0077](0077-human-review-only-final-decision-source.md)
- [ADR-0084](0084-decision-basis-allowlist.md)
- [ADR-0090](0090-versioned-human-decision-action-mapping.md)
- [ADR-0097](0097-human-confirmed-poc-quick-review.md)
