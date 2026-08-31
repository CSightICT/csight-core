# ADR-0113: RTX 4090 Qwen candidates fail closed behind one qualification gate

- Status: Accepted
- Date: 2026-08-30

## Context

The current private LLM profile uses a Community `Qwen3.8-27B` W4A16 artifact. It ran on one
RTX 4090, but its observed free VRAM fell to 254 MiB, its quantization recipe and calibration digest
are not pinned, and its original 100-case evaluation mixed an ambiguous requested-action contract
with legacy metrics. Those results are useful as a reproducible Shadow baseline but do not establish
product-release eligibility.

The official Qwen3.8-27B BF16 and FP8 weight files are larger than the 24,564 MiB device before KV
cache and runtime allocations. The official Qwen3-8B-FP8 fits the hardware preflight, but it is a
different model and cannot silently replace the 27B candidate. A runtime upgrade also changes the
tested system and must not be conflated with a model comparison.

## Decision

1. The frozen candidate matrix at `evaluation/llm/qwen4090_candidate_matrix_v1.json` is the
   machine-readable source for artifact revision, runtime image digest, serving profile, measured
   evidence, and absolute release thresholds.
2. Official 27B BF16 and FP8 candidates are `HARDWARE_EXCLUDED` when weight bytes alone exceed the
   target device. The existing Community 27B W4A16/vLLM 0.26.0 profile remains the sole `BASELINE`
   and is `SHADOW_ONLY` until every missing provenance, quality, workflow, and headroom gate passes.
3. A CSight-owned W4A16 artifact derived from the exact official 27B base is the quality-first
   challenger. Its artifact digest, base revision, quantization recipe, calibration dataset,
   dependency lock, SBOM, and qualification result digest must all be pinned. No official Qwen-owned
   27B W4 artifact is assumed to exist.
4. Official Qwen3-8B-FP8 is a separate model challenger. vLLM 0.28.0 is a separate runtime
   challenger. Model and runtime changes are qualified independently; neither may be an automatic
   fallback for the other.
5. Release comparison uses the unambiguous synthetic
   `llm_extraction_v2/2.0.0` 160-record asset and its frozen digest. The legacy v1 action and missing
   metrics are retained as history but cannot satisfy the v2 release gate.
6. `verify_qwen4090_candidates.py` validates the matrix and dataset digest and reports every
   candidate. `--require-eligible` fails unless at least one candidate satisfies all provenance,
   exact RTX 4090, safety, quality, 100-case Shadow, 20/20 terminal workflow, 2 GiB free VRAM,
   latency, throughput, soak, reliability, and metadata gates.
7. `evaluate_extraction_v2_qwen.py` is the approved synthetic extraction harness. It enforces exact
   candidate identity, repeatable Dev, threshold-gated profile freeze, and a single sealed Test.
   Result packages contain metrics and privacy-safe observations only and are digest-verified before
   freeze. Local `nvidia-smi` samples are evidence only when the runner executes on the GPU host.
8. Runnable Model and Runtime challengers have separate JSON Compose overlays. A verifier derives
   the expected image, artifact, revision, served alias, context, concurrency, memory utilization,
   KV dtype, language-only mode, and disabled-thinking command from the matrix. The launcher accepts
   only those two candidate IDs, applies `SHADOW` labels, and requires an authenticated exact alias
   canary after health. It never rewrites Core provider settings or starts two candidates together.
9. Passing the matrix gate still does not activate a model. A release-eligible manifest must be
   canonical JSON signed with the configured Ed25519 release key, then registered immutably by an
   administrator. PRIMARY and SHADOW activation are separate tenant-scoped append-only events with
   an idempotency key and compare-and-swap expected-current ID. Rollback is a new activation event;
   stored manifests and activation history cannot be updated or deleted.
10. When `MODEL_RELEASE_ENFORCEMENT=true`, a Worker fails startup unless PostgreSQL, the pinned
    public key/key ID, exact 40-character artifact revision, artifact digest, runtime-image digest,
    dependency-lock digest, and SBOM digest are all configured. Before each v2 provider call it
    requires an active release for the run's tenant and execution mode, re-verifies the signature,
    and compares the complete runtime/prompt/schema identity. Any absence or mismatch terminates the
    attempt without a provider call. Non-local vLLM cannot start with enforcement disabled.
11. A runnable candidate must use an absolute owner-controlled host model cache and pass a live
    privacy-safe host preflight before Compose starts. The preflight requires Linux x86_64, exactly
    one idle RTX 4090 with compute capability 8.9 and the exact VRAM profile, NVIDIA Container
    Runtime, an assigned Tailscale CGNAT bind, owner-only secrets/evidence storage, the exact local
    image digest, a fully hashed Hugging Face snapshot at the frozen revision, safetensors byte
    parity, dependency lock, SBOM, quantization recipe, and calibration digest. Initial collection
    may produce `EVIDENCE_COLLECTED_NOT_PINNED`; only an exact matrix-pinned `PASS` may launch.
    Dependency-lock parity is measured from the exact local image with pull disabled and network
    removed; the SBOM identifies that image digest, while recipe and calibration evidence identify
    the exact artifact revision.
    Hugging Face Hub and Transformers offline modes are mandatory during the candidate start so no
    remote byte can replace the staged and hashed snapshot.

## Consequences

- A new checkpoint, quantization, runtime version, context size, or memory utilization cannot inherit
  an older profile's qualification.
- Hardware-incompatible candidates are rejected without risking an OOM load attempt.
- Today the matrix intentionally reports `NO_RELEASE_ELIGIBLE`; this is a safe product state rather
  than a failed demo state because Core continues to use the mock provider unless explicitly
  configured otherwise.
- A tag, model name, `/v1/models` alias, Docker health response, or previously populated named
  volume is not artifact identity evidence. Candidate startup is blocked until staged host bytes
  and package evidence match the reviewed matrix.
- The API can register and inspect signed release records only when the verification key is
  configured. This does not create a signing key, sign a candidate, or turn an ineligible candidate
  into an eligible one. The current Mock demo path keeps enforcement disabled.
- The next GPU work is evidence collection, not automatic activation: generate the owned 27B W4A16
  challenger, run the v2 comparison on the exact 4090 profile, and complete the workflow and fault
  gates.

## Related decisions

- [ADR-0103](0103-limited-pilot-execution-isolation-and-shadow-mode.md)
- [ADR-0112](0112-customer-derived-analysis-text-erasure.md)
