# ADR-0119: Bind the actual MinIO version backup into the restore set

- Status: Accepted
- Date: 2026-08-30

## Context

The first restore-manifest contract bound a PostgreSQL base backup, WAL archive, MinIO version
inventory, and runtime identity manifest. The actual MinIO object-version backup was only described
by the inventory and was not itself hashed into the recovery set. A correct inventory could
therefore coexist with a missing or modified object backup and still pass pre-restore verification.
The manifest also rejected every zero-byte file, although a valid PostgreSQL physical base backup
contains empty control/configuration files inside an otherwise non-empty tree.

## Decision

- `csight.restore_manifest/2.0.0` contains exactly five bound roles: PostgreSQL physical base
  backup, PostgreSQL WAL archive, MinIO version inventory, actual MinIO version backup, and the
  runtime policy/model/prompt/settings identity manifest.
- Every role is bound by deterministic SHA-256 tree digest, file count, and total bytes. Symlinks,
  special files, missing roles, empty trees, unknown fields, binding changes, and concurrent file
  mutation fail closed. A zero-byte regular file is allowed only when the complete role has non-zero
  bytes.
- The isolated qualification uses digest-pinned PostgreSQL and MinIO on an internal-only network.
  It verifies the physical base with `pg_verifybackup`, restores a row created after the base backup
  through archived WAL, and restores raw MinIO version storage so content versions, version IDs, and
  delete markers are preserved and independently re-inventoried.
- A deliberately modified copy of the actual MinIO version backup must fail manifest verification
  before any restore target reads it.
- Local synthetic qualification never sets the production restore gate. An encrypted immutable
  off-host copy, independent key resolution, target pilot hardware, customer-scale data, and a
  second operational drill remain required.

## Consequences

- The prior four-role manifest is superseded for new recovery sets; it is insufficient evidence for
  a pilot release because it does not bind the actual object backup.
- The repository can reproduce a real physical PostgreSQL/WAL and MinIO version/delete-marker
  restore without touching the demo runtime or performing an external business action.
- The local RPO/RTO measurement demonstrates procedure correctness only. It is not evidence for
  backup scheduling, encrypted off-host durability, production data volume, or operator response
  time.

## Related decisions

- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0108](0108-retention-purge-and-evidence-reconciliation.md)
- [ADR-0114](0114-terminal-customer-content-erasure.md)
- [ADR-0118](0118-bounded-automatic-sensitive-retention.md)
