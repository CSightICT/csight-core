# Privacy and Evidence lifecycle operator runbook

## Scope and safety boundary

This runbook covers tenant-scoped expiry of customer inquiry prose, its LLM/search/grounding derivatives,
human free-form rationale, terminal customer snapshots and communication text, plus consistency repair
between `case_evidence` and the private MinIO bucket. It does not delete Cases, execution lineage,
decisions, reports, policy versions, or model metadata; it redacts bounded content fields while retaining
their PII-free identity and integrity receipt.
It does not provide a general-purpose object cleanup command.

The command is always dry-run unless `--execute` is present. Execution also requires an exact repeat
of the tenant UUID. Object deletion needs a third, separate flag. Use the runtime database role for
the operator process; do not substitute the schema-owner URL to bypass RLS qualification.

## Preconditions

1. Database migration head is at least `20260830_0029_terminal_content_erasure`.
2. `DATABASE_URL`, private MinIO settings, and the tenant's explicit
   `SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION` and `SENSITIVE_PAYLOAD_RETENTION_DAYS` are set.
3. The supplied operator UUID resolves to an active `ADMIN` in the same active tenant.
4. A restore point exists before the first destructive run.
5. No output is copied into a customer ticket. Reports contain identifiers but no raw payloads.

## Expired customer prose

Preview one bounded batch:

```bash
.venv/bin/python scripts/run_privacy_lifecycle.py \
  --env-file .env \
  --tenant-id TENANT_UUID \
  --operator-id ADMIN_USER_UUID \
  --limit 500 \
  purge-sensitive
```

Review `planned_count`, `blocked_count`, and `truncated`. Apply only the reviewed tenant batch:

```bash
.venv/bin/python scripts/run_privacy_lifecycle.py \
  --env-file .env \
  --tenant-id TENANT_UUID \
  --operator-id ADMIN_USER_UUID \
  --limit 500 \
  --execute \
  --confirm-tenant-id TENANT_UUID \
  purge-sensitive
```

Each successful item clears `case_sensitive_payloads.customer_message`, replaces the compatibility
copy with `[PURGED_BY_RETENTION]`, and redacts LLM prose, generated queries, grounded prose, provider
failure messages, human rationale/action payloads, Case attributes, terminal customer/order/delivery
snapshots, and simulated communication text. Decision, report, and communication hashes are recomputed.
Run/model/prompt/policy/index lineage, policy citations, metrics, staff/decision identity, terminal state,
and the source SHA-256 tombstone remain. One PII-free event contains bounded row counts, opaque before/after
hash transitions, the policy version, and a receipt digest. Digest or dual-write mismatch is blocked without
mutation, and deferred database guards reject content restored after purge. Re-running a completed batch
does not create a second purge event.

## Automatic expired-prose retention for the single-customer pilot

The automatic process is opt-in and narrower than the operator command. It can redact only expired
database prose and derivatives; it cannot reconcile Evidence rows or delete any MinIO object. Before
enabling it, run the manual dry-run above and resolve every blocked item.

Set the customer-approved retention pair and exact deployment tenant UUID:

```text
PRIVACY_LIFECYCLE_AUTOMATION_ENABLED=true
PRIVACY_LIFECYCLE_TENANT_ID=TENANT_UUID
SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION=customer-contract/version
SENSITIVE_PAYLOAD_RETENTION_DAYS=APPROVED_DAYS
PRIVACY_LIFECYCLE_INTERVAL_SECONDS=3600
PRIVACY_LIFECYCLE_BATCH_SIZE=500
PRIVACY_LIFECYCLE_MAX_BATCHES_PER_SWEEP=20
```

Non-local startup also requires `DATABASE_RLS_REQUIRED=true` and the API runtime database role.
Run one observed sweep first:

```bash
make retention-once
```

Expected success is exit 0 with `blocked=0` and `truncated=false`. The lifecycle event has no human
actor and records `initiator=SYSTEM_RETENTION_SCHEDULER`. Start the periodic profile only after the
result and alert receiver are reviewed:

```bash
make retention-start
```

Stop it with `make retention-stop`. Missing, stale, blocked, or truncated health state makes the
container unhealthy. Structured logs contain aggregate counts only. Any
`privacy_retention_sweep_attention_required` or unhealthy state is a stop condition; do not raise
batch limits until the specific integrity problem has been investigated through the admin dry-run.

## Evidence consistency

Preview stale rows, missing objects, and orphan candidates:

```bash
.venv/bin/python scripts/run_privacy_lifecycle.py \
  --env-file .env \
  --tenant-id TENANT_UUID \
  --operator-id ADMIN_USER_UUID \
  --limit 500 \
  reconcile-evidence \
  --stale-after-minutes 60
```

Apply DB-only recovery. This can promote a valid stale upload or mark a missing/mismatched upload
failed, but it cannot delete an object:

```bash
.venv/bin/python scripts/run_privacy_lifecycle.py \
  --env-file .env \
  --tenant-id TENANT_UUID \
  --operator-id ADMIN_USER_UUID \
  --limit 500 \
  --execute \
  --confirm-tenant-id TENANT_UUID \
  reconcile-evidence \
  --stale-after-minutes 60
```

After reviewing the new dry-run, explicitly permit deletion of failed-row and canonical orphan
objects:

```bash
.venv/bin/python scripts/run_privacy_lifecycle.py \
  --env-file .env \
  --tenant-id TENANT_UUID \
  --operator-id ADMIN_USER_UUID \
  --limit 500 \
  --execute \
  --confirm-tenant-id TENANT_UUID \
  reconcile-evidence \
  --stale-after-minutes 60 \
  --delete-orphan-objects
```

The job never deletes a malformed or unattributable key. A deletion writes a request event, lists all
versions for the exact key, deletes each payload version and delete marker by version ID, and lists the
key again. It writes completion only when zero versions remain. Inventory failure/truncation, deletion
failure, or a remaining version returns a fixed blocked reason without exposing the provider error.

## Verification and stop conditions

- Re-run the same dry-run. Expected result is no actionable findings for the processed batch.
- `blocked_count > 0` requires investigation; do not increase automation scope.
- `truncated=true` means another bounded pass is required and is not a consistency success claim.
- A missing payload row, dual-write mismatch, noncanonical object key, or missing parent Case is a
  stop condition.
- After any completed sensitive purge, migration downgrade is intentionally blocked because deleted
  prose cannot be reconstructed.

The limited pilot is not qualified until the automatic expired-prose path and the separate manual
PostgreSQL/MinIO reconciliation are exercised on the target host, alert delivery is observed, and the
restore drill is independently completed.
