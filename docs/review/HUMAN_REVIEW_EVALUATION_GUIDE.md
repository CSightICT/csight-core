# Human Review Workflow Evaluation Guide

The synthetic `human_review_workflow_v1` dataset contains 90 records: Dev 60 and sealed Test 30.
It covers all five task types, claim/release/evidence/resume/escalate/resolve, Admin/Reviewer/Viewer,
valid and invalid basis, duplicate event/resolve, concurrent claim, versioned mapping, recommendation
relations, and tenant violations.

## Protocol

1. Build and validate the dataset and immutable hash.
2. Evaluate Dev, inspect failures, then freeze the profile.
3. Execute sealed Test once with `--sealed-test`.
4. Verify stored artifacts thereafter; do not rerun Test.

Commands are exposed as `make build-human-review-evaluation`,
`make validate-human-review-evaluation`, and `make evaluate-human-review-workflow`. The last command
reruns Dev and verifies the already sealed artifacts.

## Required gates

Mapping, priority, transition, authorization, assignment, basis, outcome relation, audit completeness,
and replay must equal 1.0. Cross-tenant, unauthorized/worker/policy-created decision, duplicate task
or decision, unknown citation, wrong-run basis, and overwrite counts must equal zero.

This dataset validates deterministic implementation contracts against synthetic scenarios. It is not
evidence of real company-policy accuracy, legal correctness, real Vision quality, or reviewer UX.
