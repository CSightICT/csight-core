# Limited-pilot PostgreSQL roles and RLS activation

This runbook is a deployment gate, not a local-development default. The limited pilot must never run
API, Worker, or Dispatcher with the schema-owner/superuser URL.

## 1. Apply schema with the migration owner

Inject `MIGRATION_DATABASE_URL` from the on-prem secret mechanism and run `make migrate`. Migration
`20260829_0020_postgres_rls_roles` creates only three inert `NOLOGIN` group roles; it contains no
password and creates no login principal.

## 2. Provision login principals outside source control

Create three independent password files in the on-prem secret mechanism. Each file must be regular,
UTF-8, one line, at least 32 bytes, `0600` or stricter, and must contain a different password. Export
only their **paths** as `API_DATABASE_PASSWORD_HOST_FILE`, `WORKER_DATABASE_PASSWORD_HOST_FILE`, and
`DISPATCHER_DATABASE_PASSWORD_HOST_FILE`; do not export password values.

With `MIGRATION_DATABASE_URL` supplied only to the operator shell, run:

```bash
make provision-runtime-logins
```

The provisioner creates or safely rotates `csight_api_login`, `csight_worker_login`, and
`csight_dispatcher_login`, validates all unsafe PostgreSQL flags, and grants memberships equivalent to:

```sql
GRANT csight_api_role TO <api_login_role>;
GRANT csight_worker_role TO <worker_login_role>;
GRANT csight_dispatcher_role TO <dispatcher_login_role>;
```

Each login principal must be `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and
`NOBYPASSRLS`. Do not put the role creation statement, password, full connection URL, or secret-tool
output in Git, logs, or this runbook.

The provisioner never accepts passwords as CLI values and never prints passwords or full URLs. Custom
login names may be supplied through `API_DATABASE_LOGIN`, `WORKER_DATABASE_LOGIN`, and
`DISPATCHER_DATABASE_LOGIN` and must match the strict Compose overlay.

Start the strict runtime with:

```bash
make up-rls
```

`infra/compose.rls.yml` supplies password-less container URLs, mounts password files as Docker secrets,
and forces `DATABASE_RLS_REQUIRED=true` for API, every Worker lane, and Dispatcher. The migration owner
remains available only to the explicitly invoked migrator. `make up` and the macOS one-click controller
remain local demo compatibility mode and are not limited-pilot evidence.

## 3. Verify before application smoke

For each runtime login, verify the current principal and flags without printing its connection URL:

```sql
SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname = current_user;
```

Then run the disposable PostgreSQL RLS integration test. It provisions three real LOGIN principals
from temporary private secret files; its acceptance proof intentionally omits
the application tenant predicate and requires one tenant row, zero cross-tenant rows, zero rows with
missing context, a rejected cross-tenant insert, and Dispatcher denial on `cases`.

## 4. Terminal dispatch failure contract

The strict Dispatcher no longer touches an analysis, retrieval, grounding, or policy-evaluation run
after exhausting publication attempts. It terminalizes only the fenced Outbox row. Migration 0021's
`SECURITY DEFINER` trigger then appends a PII-free `operational_failures` record, while the source run
remains queued for an authenticated replay or cancellation decision. The Dispatcher still has no
Case or run-table access.

Verify this contract with:

```bash
RUN_CORE_INTEGRATION=1 uv run pytest -q \
  tests/integration/test_postgres_rls_roles.py \
  tests/integration/test_failure_recovery_postgres.py
```

The 2026-08-30 disposable PostgreSQL run passed 10 tests, including terminal dispatch failure,
cross-tenant omission, replay/cancel idempotency, and recovery-event fencing.

The 2026-08-30 strict Compose qualification also started API, all three Worker lanes, and Dispatcher
with the three distinct LOGIN principals. All service health checks passed, each process reported its
expected `current_user`, and local/public Web health remained normal. Temporary qualification secrets
were deleted and the default demo runtime was restored afterward.

## 5. Remaining activation blockers

The login/secret/Compose activation path is implemented and one strict start/health qualification has
passed. Do not qualify the pilot until authenticated real-API login/list/mutation, terminal failure,
replay, and lease recovery all pass in the same strict overlay, and until the current broad API/Worker
grants are reduced to an approved least-privilege matrix. The default demo Compose still uses the owner
URL fallback and `DATABASE_RLS_REQUIRED=false`; it is intentionally not activation evidence even though
all 65 current tenant tables have `ENABLE` and `FORCE` RLS.

The owner/superuser compatibility path bypasses RLS and cannot be used as evidence for this gate.
