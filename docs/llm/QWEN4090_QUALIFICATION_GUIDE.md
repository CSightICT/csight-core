# RTX 4090 Qwen extraction qualification guide

This runbook turns one candidate in the frozen RTX 4090 matrix into comparable synthetic extraction
evidence. It does not activate a model and it does not by itself satisfy the full product release
gate.

## Safety boundary

- Use only `evaluation/llm_extraction_v2/gold.jsonl`; do not copy real customer inquiries into the
  qualification asset.
- The runner sends synthetic text to the selected private vLLM endpoint. Result files retain only
  aggregate metrics and per-record booleans, latency, token counts, and bounded error codes. They do
  not retain input text, model predictions, provider responses, request IDs, or reasoning.
- Candidate ID, artifact revision, served model name, prompt hash, dataset digest, runtime image
  digest, and profile digest are fail-closed. A hardware-excluded candidate cannot run.
- Dev may be repeated while tuning. Test is sealed and may run once only after a passing Dev profile
  is frozen. Never tune a model or prompt from Test results.
- This extraction run does not create a policy decision, human decision, refund, email, payment, or
  other external business action.

## 1. Inspect candidates

```bash
make verify-qwen4090-candidates
make audit-qwen4090-hub
```

The current matrix contains the Community 27B W4A16/vLLM 0.26.0 baseline, its vLLM 0.28.0 runtime
challenger, and the official Qwen3-8B-FP8 model challenger. Official 27B BF16 and FP8 are hardware
preflight exclusions. Add a CSight-owned 27B W4A16 candidate only after its real artifact revision,
content digest, calibration digest, and recipe digest exist; never add a placeholder revision.

The Hub audit is an online metadata gate: it verifies exact commit resolution, license, quantized
base-model lineage, every safetensors LFS identity, and aggregate weight bytes. It does not replace
the offline host preflight, which hashes the actual staged bytes and runtime package.

## 2. Stage and prove the exact host package

The runnable path does not download an opaque model into a Docker-only cache during startup.
Create an owner-controlled absolute host cache, pre-stage the exact Hugging Face snapshot revision,
and generate the runtime dependency lock and CycloneDX or SPDX JSON SBOM. The private runtime env
must be a regular owner-only file and contain:

```dotenv
LLM_MODEL_CACHE_DIR=/srv/csight/hf-cache
QWEN4090_SNAPSHOT_DIR=/srv/csight/hf-cache/hub/models--ORG--REPO/snapshots/EXACT_REVISION
QWEN4090_DEPENDENCY_LOCK_FILE=/srv/csight/release-evidence/runtime-lock.txt
QWEN4090_SBOM_FILE=/srv/csight/release-evidence/runtime-sbom.cdx.json
QWEN4090_QUANTIZATION_RECIPE_FILE=/srv/csight/release-evidence/recipe.json
QWEN4090_CALIBRATION_MANIFEST_FILE=/srv/csight/release-evidence/calibration.json
QWEN4090_PREFLIGHT_OUTPUT_DIR=/srv/csight/release-evidence/host-preflight
LLM_HF_HUB_OFFLINE=1
LLM_TRANSFORMERS_OFFLINE=1
```

Set the env file to mode `0600` and the output directory to `0700`. The bind address must be an IP
assigned locally in the Tailscale `100.64.0.0/10` range and the API key must be a non-placeholder
secret of at least 32 characters. Pre-pull the exact matrix image by digest; a tag-only local image
is insufficient. Both Hugging Face Hub and Transformers offline flags are mandatory so candidate
startup cannot fetch or substitute remote bytes after preflight.

Collect evidence before adding previously unknown digests to the matrix:

```bash
make collect-qwen4090-host-evidence \
  QWEN4090_RUNTIME_ENV_FILE=infra/llm/.env.llm \
  QWEN4090_CANDIDATE_ID=qwen3-8b-fp8-official-vllm026
```

This checks Linux x86_64, exactly one RTX 4090, compute capability 8.9, exact 24,564 MiB profile,
minimum free VRAM, zero active compute processes, Docker's NVIDIA runtime, local private bind,
runtime image digest, every staged snapshot file, safetensors byte count, dependency lock, SBOM,
recipe, and calibration manifest. Raw GPU UUID, API key, bind IP, host name, and file paths are not
written; GPU UUID and bind IP appear only as SHA-256 values. Each JSON output is created once with
mode `0600`.

The dependency lock must be canonical `pip freeze --all --local` output from the exact image. The
collector runs that image with `--pull=never`, no network and no GPU service, then requires digest
parity with the supplied lock. The SBOM must identify the exact runtime image digest. Recipe and
calibration JSON must identify the exact artifact revision; the calibration evidence records its
declared dataset digest rather than the manifest-file digest.

The first valid collection intentionally reports `EVIDENCE_COLLECTED_NOT_PINNED` while matrix
package digests are null. Review the generated evidence, add the exact values through a normal code
review, then rerun `make verify-qwen4090-host`. Only `PASS` is allowed to start a candidate.

When the Linux host does not provide the repository's Python 3.12/`uv` runtime, run the same probe
inside the already pinned candidate image. The wrapper uses host networking, the host PID namespace,
the NVIDIA runtime, and the Docker socket so an existing GPU process cannot be hidden by container
PID isolation. It mounts the model package read-only and never pulls an image:

```bash
infra/llm/run_qwen4090_host_preflight_container.sh \
  qwen38-27b-awq-int4-community-vllm028 \
  /absolute/path/to/private-runtime.env \
  collect-unpinned
```

Use `strict` instead of `collect-unpinned` after every reviewed package and provenance digest is
pinned. `shadow` is the only permitted exception: it accepts
`SHADOW_READY_PROVENANCE_INCOMPLETE` when every host, artifact, runtime, lock, SBOM and recipe check
passes and the sole warning is an upstream calibration revision that was not disclosed. This status
is never `strict_ready`, never release eligible, and cannot be used for PRIMARY activation.

## 3. Start exactly one matrix-verified Shadow candidate

Two runnable overlays are committed and checked against the matrix. Verify them before every start:

```bash
make verify-qwen4090-compose-profiles
```

Then start one candidate on the authorized 4090 node. The launcher accepts strict preflight or the
explicit Shadow-only undisclosed-calibration status described above; all other warnings fail closed:

```bash
make start-qwen4090-candidate \
  QWEN4090_RUNTIME_ENV_FILE=infra/llm/.env.llm \
  QWEN4090_CANDIDATE_ID=qwen38-27b-awq-int4-community-vllm028
```

Alternatively, select `qwen3-8b-fp8-official-vllm026`. The launcher accepts no other name, reruns
the profile verifier and strict live host preflight, merges only the selected JSON override with the
private baseline Compose, waits for container health, and calls authenticated `/v1/models` inside
the container. It never pulls an unproven model as part of startup. The exact served alias must be
the sole model returned. Candidate labels always say `SHADOW`; this does not change Core to PRIMARY.

On a host without repository Python 3.12/`uv`, set `QWEN4090_TOOLING_MODE=container`. Verification
then runs in the candidate's already pinned image with `--pull=never`; candidate serving and the
resulting identity contract are unchanged.

Starting a candidate replaces the single `qwen38` service in the `csight-llm` Compose project. Stop
it without removing the named model cache:

```bash
make stop-qwen4090-candidate QWEN4090_RUNTIME_ENV_FILE=infra/llm/.env.llm
```

Run `infra/llm/serve_qwen38.sh` with the same private env file to restore the historical v0.26.0
baseline. Do not run two candidates concurrently on the single 4090.

If another CSight VLM already owns the single GPU, use an explicitly approved maintenance window
instead of stopping it by hand. `run_qwen4090_maintenance_dev.sh` refuses to run without
`ALLOW_VLM_MAINTENANCE=YES`, verifies the exact running VLM image and health, and installs an EXIT
trap before stopping it. Candidate failure, evaluation failure, SIGINT, and normal completion all
stop the candidate, restore the original VLM Compose service, and require its health endpoint to
recover. On candidate failure it captures the last 400 Compose log lines in a unique mode-0600 file
below the private result root before container removal. The runner performs Dev only; it cannot
freeze or open sealed Test.

## 4. Create a private client configuration

Create an ignored file such as `.env.qwen4090-eval` on the authorized machine. Do not commit it.

```dotenv
LLM_PROVIDER=vllm
LLM_BASE_URL=http://PRIVATE_GPU_HOST:18000/v1
LLM_API_KEY=REDACTED
LLM_MODEL_ID=EXACT_SERVED_MODEL_NAME_FROM_MATRIX
LLM_MODEL_VERSION=QUALIFICATION_PROFILE_VERSION
LLM_MODEL_REVISION=EXACT_40_CHARACTER_ARTIFACT_REVISION
LLM_TEMPERATURE=0
LLM_TLS_VERIFY=false
```

Private HTTP is acceptable only on the isolated Tailscale path already used by the node. Use TLS
verification for a TLS endpoint. The runner never prints the API key.

## 5. Run repeatable Dev

```bash
make evaluate-extraction-v2-qwen \
  QWEN4090_ENV_FILE=.env.qwen4090-eval \
  QWEN4090_CANDIDATE_ID=qwen38-27b-awq-int4-community-vllm028
```

Outputs are written below
`evaluation/results/qwen4090_extraction_v2/<candidate-id>/`. The runner revalidates the complete
dataset file digest and candidate matrix before calling the endpoint. When it runs on the GPU host,
it samples `nvidia-smi` every 200 ms and reports GPU identity, total VRAM, and observed minimum free
VRAM. When run from a remote client without local GPU access, the hardware probe is explicitly
`NOT_AVAILABLE` and cannot be used for the 2 GiB release headroom claim.

Dev must meet all current absolute quality and safety thresholds before freezing. A failed Dev is a
model or prompt diagnosis, not a reason to weaken the gate.

## 6. Freeze Dev, then run sealed Test once

```bash
make freeze-extraction-v2-qwen \
  QWEN4090_CANDIDATE_ID=qwen38-27b-awq-int4-community-vllm028

make evaluate-extraction-v2-qwen-test \
  QWEN4090_ENV_FILE=.env.qwen4090-eval \
  QWEN4090_CANDIDATE_ID=qwen38-27b-awq-int4-community-vllm028
```

Freeze re-computes the result digest across metrics and privacy-safe observations, verifies profile
and dataset identity, and refuses tampered or incomplete packages. Test refuses a changed profile
or an existing Test result manifest.

## 7. Complete the separate product gates

Extraction Test evidence is necessary but insufficient. Before changing PRIMARY, collect and pin:

1. exact artifact content, quantization recipe, calibration, dependency-lock and SBOM digests;
2. exact local RTX 4090 GPU evidence with at least 2 GiB observed free VRAM;
3. 100-case application Shadow comparison and 20/20 terminal Core workflows;
4. at least 20 minutes of soak with OOM, restart, stall, duplicate terminal, and metadata failures at
   zero;
5. timeout, 429, 5xx, malformed-output, circuit half-open and recovery evidence; and
6. an Ed25519-signed release manifest registered through the administrator API, plus the Worker
   startup and per-tenant runtime identity guard.

Only after the matrix contains all of that evidence may `make require-qwen4090-release` pass. A
passing extraction result is never copied directly into PRIMARY and never enables automatic
cross-model fallback.

## 8. Register and activate only a release-eligible result

After every preceding gate passes, an offline release process creates the strict
`llm_release_manifest/1.0.0` document and signs its canonical JSON bytes with the approved Ed25519
private key. CSight stores only the manifest, signature, key ID, actor, and append-only activation
events; the private signing key never belongs on the API or Worker host.

An authenticated administrator registers the signed document at
`POST /api/v1/operations/model-releases`, then activates its release ID at
`POST /api/v1/operations/model-releases/{release_id}/activate` with an `Idempotency-Key`, execution
mode, reason, and expected current activation ID. Current state is read from
`GET /api/v1/operations/model-activations/active`. Rollback uses the same activation endpoint to
append an event pointing to the prior release; no history is overwritten.

Do not configure `MODEL_RELEASE_ENFORCEMENT=true` until a real release-eligible manifest and public
verification key exist. With enforcement enabled, an absent activation, invalid signature, or any
artifact/runtime/prompt/schema mismatch ends the v2 attempt with zero provider calls.
