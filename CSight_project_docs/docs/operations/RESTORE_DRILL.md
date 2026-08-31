# CSight Restore Drill Runbook

## 1. Status and recovery objectives

This runbook covers an isolated, non-production recovery of PostgreSQL, its WAL archive, private
MinIO object versions, and the exact policy/model/prompt/settings versions required to interpret
the restored records.

| Item | Target or current result |
|---|---|
| Recovery point objective (RPO) | 60 minutes maximum accepted data loss |
| Recovery time objective (RTO) | 240 minutes from incident declaration to acceptance decision |
| Manifest build/verify utility | v2 binds all five artifacts; unit and tamper gates `PASS` |
| Isolated synthetic backup capture | `PASS` on 2026-08-30; digest-pinned local qualification |
| Isolated PostgreSQL restore and WAL replay | `PASS`; `pg_verifybackup` and post-base row replayed |
| Isolated MinIO version restore | `PASS`; 4 content versions and 1 delete marker matched |
| Timed local synthetic drill | `PASS`; measured RPO 0.0462 min and RTO 0.2944 min |
| Encrypted immutable off-host drill on pilot hardware | `NOT_RUN` |

An offline fixture or a successful manifest verification is not evidence that either recovery
objective has been met. Only a timed drill against an isolated target may change the actual drill
rows from `NOT_RUN`.

## 2. Recovery set and PII boundary

One recovery set uses one `backup_id` and contains all five non-empty artifact roles:

1. a PostgreSQL physical base backup;
2. the WAL archive needed to replay from that base backup to the declared recovery point;
3. a MinIO version inventory;
4. the actual separately protected MinIO object-version backup described by that inventory; and
5. a policy/model/prompt/settings version manifest containing identifiers and content hashes only.

The generated restore manifest records fixed role names, SHA-256 tree digests, file counts, total
bytes, the backup ID, PostgreSQL and MinIO versions, creation time, and a non-secret encryption key
identifier. It does **not** record local paths, filenames, object keys, tenant/customer identifiers,
credentials, signed URLs, connection strings, encryption keys, prompts, raw model output, or
customer content.

The encryption key identifier must be a KMS key ID or alias that an authorized operator can resolve
through the approved secret-management path. Never pass key material, a password, token, or private
key as `--encryption-key-id`. Encryption, off-host replication, immutability, retention, and access
control remain responsibilities of the backup system; the manifest does not provide encryption or
a signature by itself.

## 3. Preconditions and stop conditions

Before starting the RTO clock, assign an incident commander, restore operator, security reviewer,
and evidence recorder. Record timestamps in UTC and keep secrets out of the evidence log.

Proceed only when all of the following are available:

- an isolated network and clean storage volumes that cannot route writes to production;
- approved source and target identities delivered outside shell history and documentation;
- the encrypted five-part recovery set and its restore manifest from independent storage;
- access to the encryption key identified by the manifest, without exposing the key material;
- PostgreSQL and MinIO binaries compatible with the versions recorded by the manifest; and
- the application artifacts referenced by the runtime version manifest.

Stop and mark the drill `FAIL` if any input is missing or empty, a symlink or special file is found,
the manifest has unknown fields, a digest/count/byte total differs, the key identifier cannot be
resolved, a version is unavailable, the restore target is not isolated, or any credential appears
in output intended for the evidence log. Do not repair a recovery set in place; select a new
immutable recovery set and restart verification.

## 4. Build and independently verify the restore manifest

Capture the PostgreSQL and MinIO versions directly from the source backup evidence. Export the
runtime version artifact with policy rule/document/index versions, model artifact revisions,
prompt/schema versions, threshold/preprocess/postprocess versions, and a hash of non-secret settings.
Do not export setting values that may contain secrets or customer data.

Build a new manifest (the command refuses to overwrite an existing output):

```bash
python scripts/restore_manifest.py build \
  --backup-id '<immutable-backup-id>' \
  --postgresql-version '<postgresql-version>' \
  --minio-version '<minio-version>' \
  --encryption-key-id '<non-secret-kms-key-id-or-alias>' \
  --postgresql-base-backup '<base-backup-path>' \
  --postgresql-wal-archive '<wal-archive-path>' \
  --minio-version-inventory '<minio-inventory-path>' \
  --minio-version-backup '<minio-version-backup-path>' \
  --runtime-version-manifest '<runtime-version-manifest-path>' \
  --output '<new-restore-manifest.json>'
```

On a separate trusted host or process, reacquire the five artifacts and verify them before any
restore process reads them:

```bash
python scripts/restore_manifest.py verify \
  --manifest '<restore-manifest.json>' \
  --postgresql-base-backup '<base-backup-path>' \
  --postgresql-wal-archive '<wal-archive-path>' \
  --minio-version-inventory '<minio-inventory-path>' \
  --minio-version-backup '<minio-version-backup-path>' \
  --runtime-version-manifest '<runtime-version-manifest-path>'
```

Retain the PII-free `PASS` output, manifest binding SHA-256, backup ID, verifier version/commit, and
UTC start/end times. A non-zero exit is a hard stop.

## 5. Timed restore procedure

### Phase A — Select the recovery point (0–20 minutes)

1. Declare the incident and start the 240-minute RTO clock.
2. Select the latest complete base-backup/WAL recovery set whose declared recovery point is no more
   than 60 minutes before the incident cut-off.
3. Verify the manifest as described above, resolve the encryption key ID through the approved secret
   manager, and decrypt only into the isolated workspace.
4. Record the selected base backup start/stop times, last continuous WAL position, MinIO inventory
   cut-off, and calculated data-loss interval. If the interval exceeds 60 minutes, record RPO `FAIL`
   rather than silently choosing an unverified point.

### Phase B — Restore PostgreSQL (20–100 minutes)

1. Provision a clean PostgreSQL target compatible with the recorded major version and with no
   production network route.
2. Run PostgreSQL's physical backup verifier against the extracted base backup. Stop on any missing
   file, checksum error, unexpected tablespace, or version mismatch.
3. Configure recovery to use only the verified WAL archive. Recover to the selected timestamp or
   LSN and require an unbroken WAL chain; never skip a corrupt or missing segment.
4. Promote the isolated target only after recovery reaches the selected point. Record the actual
   replay endpoint and PostgreSQL version.
5. Run read-only integrity checks for schema migration head, tenant-scoped row counts, foreign-key
   consistency, append-only run/result relationships, outbox state, and review/decision uniqueness.
   Do not dispatch queued work during the drill.

### Phase C — Restore MinIO object versions (60–150 minutes, parallel where safe)

1. Provision a clean private MinIO target compatible with the recorded version. Keep Console,
   administrative APIs, and object APIs off public networks.
2. Restore every version and delete marker from the protected object backup into the clean target;
   do not flatten the inventory to latest objects only.
3. Generate a fresh version inventory using the same inventory schema and compare its count, total
   bytes, version IDs/delete-marker semantics, and object content digests to the verified source
   inventory. Keep object keys out of the general evidence log.
4. Sample only through authorized internal object reads. Do not issue signed URLs as part of the
   backup integrity gate.

### Phase D — Rebind exact runtime versions (150–190 minutes)

1. Deploy the application build named in the drill plan and load only the versions referenced by
   the verified runtime manifest.
2. Confirm policy document/rule/index versions, model artifact revisions, prompt/schema versions,
   threshold/preprocessing/postprocessing versions, and the non-secret settings hash.
3. Resolve runtime secrets independently from the backup. Never restore expired credentials from a
   settings export, and do not substitute an unrecorded model or policy version.
4. Keep all workers, outbox dispatchers, email, payment, refund, CRM, logistics, and other external
   side effects disabled until acceptance is complete.

### Phase E — Acceptance and RTO decision (190–240 minutes)

Run read-only or network-free checks and retain only aggregate, PII-free evidence:

- PostgreSQL reached the selected recovery point with a continuous WAL chain;
- calculated data-loss interval is at most 60 minutes;
- restored MinIO version inventory matches the verified source inventory;
- every database `AVAILABLE` evidence reference sampled has matching object bytes and SHA-256;
- migration head and all runtime policy/model/prompt/settings identifiers match the drill plan;
- tenant isolation checks return no cross-tenant objects or rows;
- append-only analysis, policy, review, decision, resolution, and report invariants hold;
- workers and external-action integrations remained disabled and performed zero side effects; and
- the acceptance decision was recorded within 240 minutes of incident declaration.

Mark RPO and RTO independently as `PASS` or `FAIL`. A functional restore completed after 240 minutes
is RTO `FAIL`; a timely restore with more than 60 minutes of data loss is RPO `FAIL`.

## 6. Evidence record and cleanup

Record the backup ID, manifest binding digest, source/target software versions, non-secret key ID,
selected recovery point, calculated data-loss minutes, elapsed recovery minutes, aggregate database
and object counts, every check status, deviations, owner, and follow-up date. Do not record raw row
values, object keys, customer content, credentials, URLs, or key material.

After evidence is approved, revoke temporary access, securely dispose of decrypted working copies
under the approved retention policy, destroy the isolated targets, and confirm production was never
mutated. File corrective work for every failure and schedule a full rerun; a partial rerun cannot
retroactively turn the original drill into `PASS`.

## 7. Automated isolated qualification

Run the reproducible local drill without changing the Core demo stack:

```bash
make qualify-restore-drill
```

The command creates an internal-only Docker project with no host ports, migrates an isolated
PostgreSQL source to the current head, captures a physical base backup and WAL archive, and snapshots
a synthetic versioned MinIO source. It then builds and verifies the five-role manifest, proves a
modified MinIO backup is rejected, starts clean restore targets, and verifies the post-base DB row,
migration head, all content-version hashes/version IDs, and delete marker. Workers, Dispatcher, and
all external actions remain absent. Success and failure both remove all qualification containers,
networks, and volumes.

The PII-free aggregate result is written to
`local-data/restore-qualification/latest/qualification-report.json`. The recovery set itself contains
synthetic database/object bytes and remains under gitignored `local-data`; do not attach it to a
ticket or general log. `encrypted_off_host_copy_qualified=false` and
`target_host_repeat_required=true` are intentional. This local PASS cannot set
`restore_drill_passed=true` in a pilot release manifest.
