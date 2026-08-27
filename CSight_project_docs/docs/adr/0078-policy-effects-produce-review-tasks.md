# ADR-0078: Policy effects produce review tasks, not decisions

- Status: Accepted
- Date: 2026-08-27

## Decision

Review-producing policy effects map deterministically through `review_task_mapping/1.0.0` to one
highest-priority task. All effects remain in its packet; none is a final outcome.

## Consequences

The mapping is immutable by version and duplicate policy-run delivery is a no-op.
