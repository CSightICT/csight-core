# ADR-0120: Generic Ed25519 signed Case intake

- Status: Accepted
- Date: 2026-08-31
- Owners: CSight Platform and Security
- Supersedes: none

## Context

ADR-0115 prevents a public or operator-supplied request from declaring itself `PILOT_LIVE`. A limited pilot
still needs a vendor-neutral way for an approved customer system to create real operational Cases without
giving the integration an interactive human session, tenant selector, or policy/decision authority.

## Decision

CSight exposes `POST /api/v1/integrations/cases` only when signed intake is explicitly enabled. Every configured
key ID maps, in deployment configuration, to exactly one source ID, tenant UUID, dedicated active service actor,
provenance label, and Ed25519 public-key file. The service actor must have no CSight roles. Neither `tenant_id`
nor `source_scope` is accepted in the JSON contract.

The sender signs this exact UTF-8 byte sequence, with LF separators and no final LF:

```text
csight-signed-case-intake/1.0.0
POST
/api/v1/integrations/cases
<X-CSight-Intake-Key-Id>
<X-CSight-Intake-Event-Id>
<X-CSight-Intake-Timestamp>
<lowercase SHA-256 of the exact raw HTTP body bytes>
```

The signature is standard base64 in `X-CSight-Intake-Signature`. The timestamp is Unix seconds and must be
within plus or minus 300 seconds of server time. Key ID, event ID, timestamp, method, path, and the raw-body
digest are therefore all authenticated. Unknown keys, malformed headers, invalid signatures, inactive tenants
or actors, actors with roles, and stale requests return the same generic 401 response and create no Case,
history, sensitive payload, or idempotency row.

Only a successfully authenticated request may create a `PILOT_LIVE` Case. It starts `RECEIVED` and unassigned;
this endpoint does not attach files, start analysis, make a policy decision, or execute an external business
action. Idempotency is derived from the configured source ID and signed event ID. An exact replay returns the
original Case with HTTP 200; reuse of an event ID with a different Case payload returns 409.

## Request contract

Required headers:

```text
Content-Type: application/json
X-CSight-Intake-Key-Id: <configured key ID>
X-CSight-Intake-Event-Id: <source-unique stable event ID>
X-CSight-Intake-Timestamp: <Unix seconds>
X-CSight-Intake-Signature: <base64 Ed25519 signature>
```

Example body shape (all values are synthetic):

```json
{
  "schema_version": "signed_case_intake/1.0.0",
  "order_ref": "DEMO-ORDER-100",
  "product_ref": "DEMO-SKU-200",
  "customer_message": "The delivered item appears damaged.",
  "requested_action": "EXCHANGE",
  "attributes": {"channel": "customer-crm"}
}
```

## Operator smoke-test example

The following is a reference procedure, not an action performed by CSight. Generate and retain the private key
on the source-system side; install only the public key in the CSight secret mount. Replace every example path,
ID, host, and UUID before use.

```sh
umask 077
openssl genpkey -algorithm ED25519 -out source-private.pem
openssl pkey -in source-private.pem -pubout -out csight-intake-public.pem
chmod 600 source-private.pem
chmod 0444 csight-intake-public.pem
```

Configure the API with a JSON `SIGNED_INTAKE_SOURCES` mapping like the documented `.env.example`, then prepare
`payload.json` without reformatting it between hashing and sending:

```sh
key_id='crm-key-2026'
event_id='crm-event-000001'
timestamp="$(date +%s)"
body_sha256="$(shasum -a 256 payload.json | awk '{print $1}')"
printf '%s\n%s\n%s\n%s\n%s\n%s\n%s' \
  'csight-signed-case-intake/1.0.0' \
  'POST' \
  '/api/v1/integrations/cases' \
  "$key_id" "$event_id" "$timestamp" "$body_sha256" > canonical.txt
signature="$(openssl pkeyutl -sign -rawin -inkey source-private.pem \
  -in canonical.txt | openssl base64 -A)"
curl --fail-with-body --data-binary @payload.json \
  -H 'Content-Type: application/json' \
  -H "X-CSight-Intake-Key-Id: $key_id" \
  -H "X-CSight-Intake-Event-Id: $event_id" \
  -H "X-CSight-Intake-Timestamp: $timestamp" \
  -H "X-CSight-Intake-Signature: $signature" \
  https://csight.example.test/api/v1/integrations/cases
```

The first successful request must return HTTP 201 and `source_scope: "PILOT_LIVE"`; repeating the exact bytes
and event ID must return HTTP 200 with the same `case_id`. Changing one body byte while reusing the signature,
or sending a timestamp older than 300 seconds, must return 401 and leave Case counts unchanged.

## Consequences

- Customer integrations can be onboarded without embedding customer-specific adapters into Core.
- Tenant authority stays in deployment configuration and PostgreSQL RLS context, not in untrusted JSON.
- Ed25519 key rotation is additive: install a new key ID, switch the source, then remove the old mapping after
  the allowed replay window and operational confirmation.
- Delivery retries are safe, but webhook queues, attachment import, automatic assignment, and workflow start
  remain explicit later slices.

## Related decisions

- [ADR-0102](0102-sensitive-payload-lifecycle-expand-phase.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0111](0111-case-intake-assignment-and-direct-object-ownership.md)
- [ADR-0115](0115-immutable-case-source-scope-and-pilot-metrics.md)
