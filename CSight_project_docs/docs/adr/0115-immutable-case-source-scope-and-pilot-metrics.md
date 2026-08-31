# ADR-0115: Immutable Case source scope and pilot-only operational metrics

- Status: Accepted
- Date: 2026-08-30
- Owners: CSight Platform and Product
- Supersedes: none

## Context

Synthetic demo Cases produce structurally valid reports and learning assets. The previous readiness and PoC
queries counted those rows together with customer operations, so 60 synthetic records could incorrectly make
drift review appear ready and internal demo outcomes could appear as pilot performance.

## Decision

Every Case receives one server-owned `source_scope` and `source_provenance` at creation. Supported scopes are
`SYNTHETIC_DEMO`, `SHADOW`, `IMPORTED`, `PILOT_LIVE`, and `NOT_ATTESTED`. Validated synthetic commerce input is
classified as `SYNTHETIC_DEMO`; ordinary input fails closed to `NOT_ATTESTED`. The public Case request cannot
claim `PILOT_LIVE`.

The two values are immutable after insert and PostgreSQL rejects updates. Review Reports copy the scope and
provenance into their hashed `data_scope`; learning assets copy them into their hashed `privacy_scope`.

Default PoC metrics, SLA evidence, distributions, drift readiness, and recent learning-asset lists include only
`PILOT_LIVE`. APIs expose eligible and excluded counts. Synthetic, Shadow, imported, and unattested records may
remain available as explicitly labelled diagnostic material but cannot establish pilot readiness.

## Consequences

- Existing synthetic rows are backfilled as `SYNTHETIC_DEMO`; other legacy rows become `NOT_ATTESTED`.
- A trusted, separately authorized intake or attestation process is required before real pilot Cases can be
  created as `PILOT_LIVE`; relabelling historical Cases is prohibited.
- With 60 synthetic assets and zero `PILOT_LIVE` assets, drift readiness remains false.
- Human decision ownership and the prohibition on real refund, payment, email, and shipping effects are unchanged.

## Verification

- Migration 0030 backfill, enum constraint, index, and immutable update trigger.
- Unit contract proving 60 synthetic learning assets cannot satisfy readiness.
- Default backend test suite, static checks, Web tests/build, live migration, and Core health checks.
