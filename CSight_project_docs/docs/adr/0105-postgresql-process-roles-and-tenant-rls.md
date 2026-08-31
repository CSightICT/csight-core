# ADR-0105: PostgreSQL process roles and transaction-local tenant RLS

- Status: Accepted
- Date: 2026-08-29

## Context

Repository predicates derived from an authenticated Principal are necessary, but a missed predicate
must not expose another customer's row in the limited on-prem pilot. API, Worker, Dispatcher, and
schema migration also have materially different database responsibilities. The existing local
deployment uses one PostgreSQL owner credential and therefore bypasses an independent database
tenant boundary.

## Decision

- `csight_api_role`, `csight_worker_role`, and `csight_dispatcher_role` are inert `NOLOGIN`,
  `NOSUPERUSER`, `NOBYPASSRLS` group roles. Deployment creates separate login principals and grants
  exactly one group role to each process; credentials stay outside source and migration files.
- Migration uses a separate owner URL. The owner/superuser URL is prohibited from limited-pilot API,
  Worker, and Dispatcher qualification.
- Every current ORM table containing `tenant_id`, plus `tenants`, enables and forces Row-Level
  Security. API and Worker policies require
  `current_setting('app.tenant_id', true)` to equal the row tenant. Missing context returns zero rows
  and writes fail closed.
- SQLAlchemy copies a validated tenant UUID into PostgreSQL with transaction-local
  `set_config(..., true)`. HTTP dependencies retain the context through the endpoint execution and
  Celery task entrypoints bind it from a schema-validated identifier-only queue payload.
- Pre-authentication never gets a table-wide exception. Tenant login lookup is limited to one exact
  normalized slug. OIDC session lookup/touch is limited to one exact SHA-256 session digest, and the
  API role may update only CSRF, activity, expiry, and revocation columns through that capability.
- A malformed queue event that retains a valid event UUID may update only that exact outbox row so
  durable quarantine remains possible without tenant-wide Worker access.
- Dispatcher has `SELECT` and `UPDATE` only on the seven durable Outbox tables and receives a global
  Outbox-only policy. It cannot query Case, identity, analysis result, policy result, review, or
  resolution tables.

## Consequences

- A query that accidentally omits its application tenant predicate still returns only the current
  transaction's tenant, and missing context returns no tenant rows.
- Transaction-local settings reset on commit/rollback, preventing pooled-connection tenant leakage.
- New tenant tables receive no runtime grant by default. Each future migration must add the table to
  the explicit RLS contract and tests.
- PostgreSQL roles are cluster-scoped. Downgrade removes database policies and grants but leaves the
  inert `NOLOGIN` group roles so another database or pre-provisioned membership is not destroyed.
- Current terminal Dispatcher failure handling also tries to transition some run tables. That path
  exceeds the strict Outbox role and is not qualified yet. Until it is moved behind a narrow stored
  procedure or Worker-owned event, the strict Dispatcher role is fail-closed and pilot activation is
  blocked; using the legacy owner credential is not an accepted workaround.
- Full API/Worker/Dispatcher migration under distinct login principals, including OIDC, poison
  events, terminal publish failure, rollback, and restore, remains a target-Mac qualification gate.

## Related decisions

- [ADR-0006](0006-principal-derived-tenant-and-local-jwt.md)
- [ADR-0009](0009-transactional-outbox-and-fenced-analysis-execution.md)
- [ADR-0093](0093-durable-resolution-and-simulation-outboxes.md)
- [ADR-0102](0102-sensitive-payload-lifecycle-expand-phase.md)
