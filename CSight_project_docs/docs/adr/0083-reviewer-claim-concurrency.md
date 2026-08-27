# ADR-0083: Reviewer claim is exclusive and concurrency-safe

- Status: Accepted
- Date: 2026-08-27

## Decision

Claims lock the tenant-scoped task and verify expected version, status, type, and role. Manager,
safety, and escalated tasks require an administrator.

## Consequences

Exactly one active assignment and one `CLAIMED` action can be created for a version.
