# ADR-0121: The limited-pilot runtime is a separate fail-closed profile

- Status: Accepted
- Date: 2026-08-31

## Context

The existing macOS controller and `compose.core.yml` are optimized for an internal demonstration.
They permit local password authentication, mock providers, a shared database owner, disabled
retention automation, disabled evidence scanning, and disabled external telemetry. Changing those
defaults in place would make tomorrow's demo fragile without proving that a real customer pilot is
safe.

The pilot also needs an operational start boundary. A syntactically valid Compose file is not
evidence that the checkout, images, disk, identity, RLS, privacy lifecycle, observability, model
release, or recovery set is qualified. Conversely, a start helper must not silently reclaim disk or
create a new backup while deciding whether it is safe to start.

## Decision

- The admitted runtime composes Core, strict RLS, Evidence security, and a final pilot overlay in a
  fixed order under the separate `csight-pilot` project name. The demo project and controller remain
  unchanged.
- The final overlay hard-enforces non-local OIDC-only authentication, secure cookies, process-role
  RLS, sanitization plus internal digest-pinned ClamAV, explicit tenant retention with the bounded
  maintenance scheduler, OTLP/HTTP configuration, signed non-mock LLM admission, non-mock Vision,
  one generic signed-intake customer source, and HTTPS Evidence presentation. Development seed and
  unqualified recovery mutations remain off.
- Signed intake is fixed on for exactly one key-to-source mapping whose tenant equals the retention
  tenant. The mapping binds one dedicated service actor and provenance to the fixed container path
  `/run/config/signed_intake_public_key.pem`; the HTTP body limit is 128 KiB and accepted clock skew
  is 300 seconds. API alone receives the mapping and read-only public-key mount. Workers,
  Dispatcher, and privacy maintenance receive neither. Key generation and private-key custody are
  outside CSight and outside this controller.
- The model Worker alone receives LLM and Vision credentials. The retrieval Worker receives only
  the LLM credential required by its current query-planning composition. API, decision Worker,
  Dispatcher, and privacy maintenance explicitly override the Core credential fields to empty.
  Non-provider processes use a `mock` configuration sentinel only to avoid constructing provider
  adapters; they do not run model tasks or produce model results.
- The pilot enables immutable model-route enforcement only for
  `PRODUCT_DEFECT_TEXT_EXTRACTION_V2`. API resolves and snapshots the active signed route for a new
  idempotent analysis; the model Worker validates that pinned historical route, its activation and
  signature, the configured deployment ID, and the exact runtime release identity before the
  provider call. API and the model Worker alone receive `MODEL_ROUTE_ENFORCEMENT=true`, and only the
  model Worker receives `MODEL_ROUTE_DEPLOYMENT_ID`.
- Three active PRIMARY route rows are not proof of three enforced runtime paths. Policy-query
  construction and grounded explanation do not yet have their own immutable snapshot and execution
  guards, so the onboarding model-route gate remains fail closed until both paths have equivalent
  runtime evidence. The profile must not be presented as full three-task route enforcement.
- One private, owner-only env file provides deployment-specific values. Runtime database passwords
  are separate owner-only files. The model signing private key and customer intake private key are
  never present; only their separate public verification keys are mounted read-only in the
  processes that require them.
- Start requires a read-only preflight. It checks a fixed minimum of 30 GiB free space, a clean exact
  release commit, non-development image tags and existing images, the merged Compose contract, all
  frozen limited-pilot gates, the current five-artifact restore-set hashes, and evidence for an
  encrypted immutable off-host schedule plus two RPO/RTO-qualified target-host restores with
  independent key resolution.
- The preflight host-command allowlist contains only Git reads, Docker information/image reads, and
  Docker Compose `config`. It performs no backup, restore, build, migration, delete, prune, log
  truncation, WAL rotation, or volume operation.
- The controller calls preflight before `up --detach --wait --no-build`. A failed preflight results
  in zero Compose start calls. Stop uses `compose stop` and preserves every named volume.
- First-time provisioning, migration, runtime-login creation, restore, and signed-model activation
  are explicit governed procedures outside this controller. The profile is never weakened to make
  bootstrap convenient.
- A local synthetic restore or manifest-only verification remains insufficient. Pilot admission
  requires the report to bind the same verified manifest and assert encrypted immutable off-host
  copy, backup scheduling, independent key resolution, two target-host drills, RPO at most one hour,
  RTO at most four hours, and zero business side effects.

## Consequences

- The internal demo remains easy to operate, while a customer pilot cannot inherit its permissive
  defaults accidentally.
- Today the pilot may correctly remain blocked by disk capacity, a dirty checkout, missing release
  images, unqualified models, or absent off-host recovery evidence. The controller reports a hard
  stop and never repairs those conditions itself.
- The separate project uses separate named volumes and therefore requires deliberate initial
  provisioning. Reusing demo data or credentials is not an accepted shortcut.
- `pilot-config` proves only Compose syntax. `pilot-preflight` is admission evidence, and successful
  process startup plus the existing live qualification gates remain additional evidence.
- Preflight proves route configuration and process scope, not a live tenant route. Missing, stale,
  unsigned, or runtime/deployment-mismatched text-extraction routes fail explicitly at new-analysis
  admission or before the model Worker calls its provider.
- This profile is still a single-host limited pilot. It does not claim high availability or a 24×7
  service-level objective.

## Related decisions

- [ADR-0103](0103-limited-pilot-execution-isolation-and-shadow-mode.md)
- [ADR-0104](0104-oidc-pkce-server-session-and-csrf.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0106](0106-opt-in-opentelemetry-pilot-observability.md)
- [ADR-0116](0116-non-local-oidc-only-authentication.md)
- [ADR-0118](0118-bounded-automatic-sensitive-retention.md)
- [ADR-0119](0119-bound-five-artifact-restore-set.md)
- [ADR-0120](0120-generic-ed25519-signed-case-intake.md)
- [ADR-0122](0122-append-only-task-model-route-plans.md)
