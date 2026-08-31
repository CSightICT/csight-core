# Pilot readiness and operator onboarding

## Safe onboarding command

Use `scripts/onboard_pilot_tenant.py` with a reviewed `pilot_onboarding/1.0.0` JSON manifest.

- `plan` validates 5–20 named accounts, administrator/reviewer staffing, explicit retention,
  signed-intake no-role actor, policy identifiers, alerts, and support inputs. Output contains only
  counts, booleans, and a configuration digest.
- `apply --output <owner-only-path>` creates or reuses the tenant, named OIDC accounts, roles, and
  no-role intake actor. It never deletes rows or roles and rejects conflicting existing identity.
  It creates a mode `0600` Secret-free environment fragment and never overwrites different content.
- `verify --output <same-path>` re-reads the identity graph, environment fragment, active policy
  index, and active rule-set activation. It returns six PII-free PASS/FAIL gates.

The public key, customer IdP metadata, approved retention values, policy corpus, alert recipients,
and off-host storage remain customer/operator inputs. Do not put private keys, client secrets,
passwords, raw inquiries, or direct customer data in the manifest.

## Runtime readiness API

`GET /api/v1/operations/pilot-readiness` is administrator-only and `no-store`. It returns:

- `configuration_ready`: all six onboarding gates pass;
- `operationally_qualified`: all 25 limited-pilot checks pass and the evidence file is fresh;
- `pilot_ready`: both values are true;
- gate kind, code, status, verification and expiry timestamps, evidence digest, and safe guidance.

`PILOT_QUALIFICATION_EVIDENCE` points to the PII-free qualification JSON. Its filesystem modified
time is the verification time. `PILOT_QUALIFICATION_EVIDENCE_MAX_AGE_HOURS` defaults to 24; expired
evidence automatically fails every operational gate.

The pilot OpenAPI artifact is `docs/openapi/pilot.openapi.json`. Regenerate it with
`uv run python scripts/generate_pilot_openapi.py`; it includes signed Case intake even when the
developer profile keeps that route disabled.

## Current admission boundary

Code and contracts do not constitute pilot qualification. Start remains prohibited until the six
configuration gates, 25 operational gates, preflight, clean immutable image digests, at least
30 GiB free disk, and off-host restore evidence all pass. Real business actions remain disabled.
