# ADR-0128: Internal human feedback may consume SHADOW analysis

- Status: Accepted
- Date: 2026-09-10
- Authority: Owner explicitly requested removal of the Shadow downstream block to use results and collect feedback.

## Decision

This supersedes ADR-0103's blanket prohibition only for explicitly enabled internal human-feedback
workflows. `SHADOW_HUMAN_FEEDBACK_ENABLED=true` is accepted only in local/test environments. Default
and separated pilot configurations retain the prohibition. This is actual existing console usage,
not a separate diagnostic viewer.

New policy runs record an immutable `shadow_feedback_allowed` permission snapshot. Database
lineage triggers admit a SHADOW root only with that snapshot and admit its tenant-scoped descendants.
Unmarked Shadow roots remain blocked; no analysis mode or existing result is rewritten. Turning
off the flag stops new feedback admission, but already admitted human work can finish.

The internal profile sends new console analyses as SHADOW and rejects PRIMARY admission. It uses
the pinned GX10 Q5 artifact, Extraction local.8 and Grounding local.2, local E3 and the existing
RAW/HYBRID/Top-3 retrieval path. There is no LLM query-builder default or automatic model fallback.
Provider failures remain explicit failures. Model outputs and matching remain unqualified advice.

Human authentication, tenant isolation, explicit final confirmation, append-only provenance and
DRY_RUN-only external actions are unchanged. Signed model promotion/release gates remain unchanged.
Feedback runs with policy/review events cannot count as clean observation-only Shadow100 evidence.
No customer pilot, E3 commercial-use rights, model accuracy, or launch approval is implied.

## Operations and rollback

The local controller opt-in marker selects a separate Compose overlay. GX10 remains authenticated
and loopback-only; an owned, key-only, host-key-verified SSH tunnel connects the Mac. The existing
service API key is passed over SSH into child-process environment without logging or persistence
on the Mac; it is visible to authorized Docker administrators as other runtime secrets are.
Passwords are not requested or used. Other GPU jobs and RTX 4090 remain untouched.

Migration 0037 is additive and defaults all historical rows to false. Downgrade is refused once
feedback history exists; disabling new admission is the non-destructive operational rollback.
Keep the schema and immutable history instead of deleting or relabelling feedback data.

The existing authenticated demo URL also serves this local console. The banner requires internal,
noncommercial test data and distinguishes unverified AI advice from human decisions and simulated
business actions. Do not treat the word `local` as proof of network isolation or customer eligibility.
