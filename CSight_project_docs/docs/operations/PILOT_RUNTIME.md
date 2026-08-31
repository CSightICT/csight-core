# CSight Limited-Pilot Runtime Runbook

## 1. Scope and current boundary

This runbook controls the single-customer, 5–20 operator limited-pilot runtime. It is not the
macOS demo controller, a high-availability deployment, a 24×7 SLA, or a mechanism for refund,
payment, email, logistics, or any other real external business action. Models and policy remain
advisory; an authenticated human remains the only final decision maker.

The admitted runtime is a separate Compose project named `csight-pilot`. It reuses the existing
Core definitions but composes four files in this exact order:

1. `infra/compose.core.yml`;
2. `infra/compose.rls.yml`;
3. `infra/evidence/compose.evidence-security.yml`; and
4. `infra/pilot/compose.pilot.yml`.

The existing `csight-core` demo project, `scripts/csight_server_control.sh`, and the macOS control
application are unchanged. Do not run the demo and pilot stacks on the same default host ports.

## 2. What the pilot overlay forces

The final overlay is additive and fail closed. It forces:

- `ENVIRONMENT=pilot`, development seed disabled, and an immutable non-`dev` image tag;
- OIDC Authorization Code + PKCE only, with legacy password/Bearer compatibility disabled, HTTPS
  issuer/endpoints, secure session cookies, and no insecure-HTTP exception;
- distinct API, Worker, and Dispatcher database login files plus mandatory RLS enforcement;
- image sanitization and the existing digest-pinned, internal-only ClamAV service;
- explicit tenant retention policy and the bounded `privacy-lifecycle` maintenance profile;
- OTLP/HTTP traces and metrics configuration;
- a signed, active non-mock vLLM release and a qualified non-mock Vision endpoint in the processes
  that execute those calls;
- fail-closed immutable model-route enforcement for `PRODUCT_DEFECT_TEXT_EXTRACTION_V2`: API
  resolves and snapshots the current signed PRIMARY/SHADOW route only for a new idempotent request,
  while the model Worker validates the pinned historical plan, activation, signature, deployment,
  and exact runtime identity before making the provider call;
- route enforcement only in API and the model Worker, with
  `MODEL_ROUTE_DEPLOYMENT_ID` present only in the model Worker;
- provider credentials only in the model Worker (LLM and Vision) and retrieval Worker (LLM), with
  explicit empty overrides in API, decision Worker, Dispatcher, and retention maintenance;
- generic Ed25519 signed intake enabled for exactly one customer source, tenant, dedicated service
  actor, provenance, and public key, with a 128 KiB body limit and 300-second clock-skew limit;
- the signed-intake public key and configuration only in API; no Worker, Dispatcher, or privacy
  process receives the intake mapping or mounts its key;
- HTTPS browser Evidence links through the approved gateway; and
- operational replay/cancel mutations disabled until their separate recovery qualification passes.

The overlay does not add Kafka, Redis, Kubernetes, ANN indexes, automatic external actions, or an
automatic model fallback.

This is deliberately not full three-task route enforcement. The database can hold active routes
for extraction, policy-query construction, and grounded explanation, but the current runtime guard
is connected only to text extraction v2. Policy-query construction and grounded explanation still
need their own immutable snapshot and execution guards. Consequently the onboarding
`PRIMARY_MODEL_ROUTES` gate remains fail closed even when three route rows are active; neither the
route count nor this profile may be presented as proof that all three runtime paths are enforced.

## 3. One-time provisioning is outside the controller

The pilot controller operates only an already provisioned and qualified runtime. It never builds
images, applies migrations, creates database roles, restores data, or changes a backup. For a new
customer environment, use an approved change window to do all of the following before runtime
admission:

1. produce and externally verify release-tagged Core and Web images;
2. provision the isolated `csight-pilot` PostgreSQL/RabbitMQ/MinIO volumes or restore them through
   the approved recovery runbook;
3. apply the migration head with the migration-owner credential;
4. provision the three non-superuser, non-`BYPASSRLS` runtime logins;
5. register and activate the signed model release for the exact runtime identity, then activate the
   tenant's `PRODUCT_DEFECT_TEXT_EXTRACTION_V2` route for each admitted execution mode with a
   deployment ID that exactly equals `MODEL_ROUTE_DEPLOYMENT_ID` on `worker-model`;
6. create one dedicated, active, no-role signed-intake service actor in the one customer tenant and
   provision the customer's Ed25519 public key through the approved out-of-band key ceremony; and
7. collect the complete limited-pilot and target-host backup/restore evidence.

Do not weaken the pilot profile to bootstrap an empty database. If provisioning is incomplete,
`pilot-up` must fail instead of falling back to the owner credential or demo authentication.

## 4. Private environment preparation

Copy the placeholder file and restrict it before adding any value:

```bash
cp infra/pilot/.env.pilot.example infra/pilot/.env.pilot
chmod 600 infra/pilot/.env.pilot
```

The real file is ignored by Git. Keep runtime passwords, OIDC/model credentials, and private paths
out of commits, terminal transcripts, tickets, and screenshots. The API, Worker, and Dispatcher
database password files must each be absolute, owner-owned, non-symlink regular files with no
group/other permission and exactly one non-empty line. The model verification public key is mounted
read-only; its private signing key never belongs on this host.

`SIGNED_INTAKE_SOURCES` must contain exactly one mapping. Its tenant must equal
`PRIVACY_LIFECYCLE_TENANT_ID`, and it must identify the separately provisioned no-role service
actor, source, provenance, and the fixed container path
`/run/config/signed_intake_public_key.pem`. Set `SIGNED_INTAKE_PUBLIC_KEY_HOST_FILE` to a separate
absolute, non-symlink Ed25519 public-key file that is not group/world writable. Only API mounts this
file. Never copy the customer's private key to CSight, and do not generate a key in the runtime
controller or preflight.

`PILOT_RELEASE_COMMIT` must equal the exact clean checkout `HEAD`. `CSIGHT_IMAGE_TAG` must identify
already built local `csight-core` and `csight-web` images and cannot be `dev` or `latest`.

## 5. Read-only preflight gates

Run:

```bash
make pilot-preflight PILOT_ENV_FILE=infra/pilot/.env.pilot
```

The preflight performs only bounded reads and hashes. It executes no shell command, backup,
restore, migration, build, delete, prune, truncate, or volume operation. It checks:

1. the private env file, exact security values, secret-file modes, approved retention pair, tenant
   UUID, the one signed-intake mapping, fixed body/clock limits, parseable separate Ed25519 public
   key, model identities/digests, route-enforcement flag, model-Worker deployment ID, and existing
   WAL archive directory;
2. at least 30 GiB of free space on the project filesystem;
3. a clean tracked and untracked worktree whose `HEAD` equals `PILOT_RELEASE_COMMIT`;
4. all 25 frozen limited-pilot qualification gates;
5. the v2 manifest and the current bytes/counts/digests of all five recovery artifacts;
6. a report bound to that same manifest proving encrypted immutable off-host scheduling,
   independent key resolution, at least two restores on the target pilot hardware, RPO at most 60
   minutes, RTO at most 240 minutes, and zero external business side effects;
7. the merged four-file Compose contract, including API-only intake configuration/key scope and
   API/model-Worker-only route enforcement with a model-Worker-only deployment ID; and
8. Docker availability plus the two already built release-tagged images.

Preflight verifies configuration and scope only; it does not query or activate a tenant route plan.
Missing, stale, unsigned, or identity-mismatched runtime routes still fail closed when API starts a
new v2 analysis or the model Worker executes its pinned stage.

The target-host restore report retains the existing
`csight.restore_drill_qualification/1.0.0` schema and must add these PII-free fields:

```json
{
  "status": "PASS",
  "scope": "encrypted-immutable-off-host-pilot-hardware",
  "encrypted_off_host_copy_qualified": true,
  "immutable_off_host_copy_qualified": true,
  "independent_key_resolution_qualified": true,
  "scheduled_backup_qualified": true,
  "target_host_repeat_required": false,
  "pilot_hardware_repeat_count": 2,
  "rpo_passed": true,
  "rto_passed": true,
  "external_business_side_effects": 0,
  "manifest": {
    "status": "PASS",
    "binding_sha256": "<same verified binding>"
  }
}
```

The local synthetic restore report intentionally has
`encrypted_off_host_copy_qualified=false`; it cannot admit this profile. A manifest verification
proves integrity of supplied bytes, not the existence of a schedule, an immutable off-host copy, or
a successful target-host recovery.

### Disk stop condition

Less than 30 GiB free is an immediate `disk_capacity` failure. The program reports that no cleanup
was run. It never calls Docker prune, deletes caches, removes images, rotates WAL, truncates logs,
or removes a volume. An operator must inspect storage, choose a recoverable cleanup or capacity
change through a separate approved action, and rerun preflight.

## 6. Start, status, and stop

Check only the merged Compose syntax:

```bash
make pilot-config PILOT_ENV_FILE=infra/pilot/.env.pilot
```

This is not release admission. Start only through the controller, which reruns the full preflight
before contacting Compose:

```bash
make pilot-up PILOT_ENV_FILE=infra/pilot/.env.pilot
make pilot-status PILOT_ENV_FILE=infra/pilot/.env.pilot
```

The start command is exactly a detached, health-gated `up --no-build` with the maintenance profile.
It never builds or migrates. If preflight exits non-zero, Compose `up` is not called.

Stop with:

```bash
make pilot-stop PILOT_ENV_FILE=infra/pilot/.env.pilot
```

Stop uses Compose `stop`. PostgreSQL, WAL, RabbitMQ, MinIO, and ClamAV named volumes are preserved.
It does not use `down`, `--volumes`, `volume rm`, or any cleanup command.

## 7. Release evidence and incident handling

Retain only the PII-free preflight result, release commit, image identities, qualification report
digests, restore binding digest, UTC timestamps, and operator/change references. Never retain raw
customer text, object keys, local evidence paths, credentials, full connection strings, or signing
material.

Failure of OIDC, RLS, retention, signed-intake admission, ClamAV, signed-model admission, v2 model
route resolution or pinned-route validation, release evidence, backup evidence, or disk capacity is
a stop condition. Do not switch to the demo profile as an operational fallback.
Provider degradation may leave model features unavailable without changing the human-only decision
boundary, but a profile that no longer satisfies admission must not be newly started.

See also:

- `docs/operations/RESTORE_DRILL.md`;
- `docs/operations/EVIDENCE_SECURITY.md`;
- ADR-0104, ADR-0105, ADR-0106, ADR-0116, ADR-0118, ADR-0119; and
- ADR-0120, ADR-0121, and ADR-0122.
