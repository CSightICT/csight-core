# RTX 4090 GGUF three-task Dev selection

This runbook compares the two unpublished CSight GGUF candidates on Dev only. The llama.cpp
candidate runs on Khrin, while the evaluator runs on the Mac. This split is intentional: the live
Query Builder score must use the existing Mac-local CSight PostgreSQL corpus and the real
Embedding service on `127.0.0.1:8091`. It must not be replaced with an in-memory or mocked
retriever.

The run does not freeze a profile, open sealed Test, activate a model, route Core traffic, or create
policy decisions, human decisions, resolutions, refunds, email, payment, delivery, or CRM actions.
A valid result may still be `NO_WINNER` when neither candidate passes every absolute task gate.

## Fixed topology

- Khrin: exactly one protected llama.cpp candidate, Tailscale-only `:18002`, existing VLM restored
  after every exit path.
- Mac: repository Python 3.12 virtual environment, CSight PostgreSQL, and
  `EMBEDDING_BASE_URL=http://127.0.0.1:8091`.
- Candidate order: mixed Q4/Q6, then imatrix Q5_K_S. The two runs share one fresh owner-only result
  root but use separate candidate directories and separate Khrin completion states.
- Runtime: context 4096, concurrency 1, temperature 0, non-thinking, no automatic fallback.

Do not start until the clean imatrix, final two GGUF files, build manifest, SBOM, quantization
evidence, and candidate matrix contain the same current digests. The local-Dev preflight is expected
to keep `artifact_revision=null` and all release, PRIMARY, Core-routing, freeze, and sealed-Test
flags false.

## 1. Pin the Mac evaluator inputs

From the repository root on the Mac, use the locked offline environment and record the three
non-secret digests:

```bash
UV_OFFLINE=1 uv run --frozen --offline python \
  scripts/run_qwen4090_candidate_dev.py inputs \
  --matrix evaluation/llm/qwen4090_candidate_matrix_v2.json
```

Use the returned `source_bundle_digest` and `dependency_lock_digest` unchanged for both candidates
and final selection. A source, dataset, policy-corpus, adapter, matrix, or lock change requires a new
result root and two new Dev runs.

## 2. Create one private Mac evaluation env per candidate

Create an absolute caller-owned mode-`0600` file outside Git. The selected model ID and version must
match the matrix candidate exactly. Leave revision and every release/routing identity absent.

```dotenv
ENVIRONMENT=local
LLM_PROVIDER=llama_cpp
LLM_BASE_URL=http://KHRIN_TAILSCALE_IPV4:18002/v1
LLM_API_KEY=OWNER_ONLY_SHARED_RUNTIME_KEY
LLM_MODEL_ID=EXACT_MATRIX_SERVED_MODEL_NAME
LLM_MODEL_VERSION=EXACT_MATRIX_CANDIDATE_ID
LLM_MAX_OUTPUT_TOKENS=1024
LLM_TEMPERATURE=0
LLM_TLS_VERIFY=false
LLM_TASK_RUNTIMES={}
MODEL_RELEASE_ENFORCEMENT=false
MODEL_ROUTE_ENFORCEMENT=false
DATABASE_URL=postgresql+psycopg://LOCAL_USER:LOCAL_PASSWORD@127.0.0.1:5432/csight
EMBEDDING_BASE_URL=http://127.0.0.1:8091
```

The driver rejects a non-Tailscale model endpoint, non-local PostgreSQL, non-local Embedding,
task-specific endpoint override, fake artifact revision, or release/routing configuration. It
accepts only the keys shown above plus bounded LLM/Embedding timeout, input/output character-limit,
and provider circuit-breaker settings. Build this as a fresh file; never copy the application
`.env`. OIDC, JWT, MinIO, signed-intake, observability, vision, reranker, and release identity keys
are rejected without echoing their names or values. The driver also sanitizes the child process
environment so shell-level application secrets cannot override this file. Reranker configuration
is not used; Query Builder remains on the production HYBRID/RRF path.

Before the GPU window, confirm the Mac database contains both evaluation tenants and the current
policy corpus, and check Embedding health. Do not copy the Mac `.env` or database credentials to
Khrin.

## 3. Hold one Khrin candidate with an owner-only completion sentinel

Deploy the exact reviewed repository files to the owner-controlled Khrin tooling directory. Khrin
must use Python 3.12 or newer for the host preflight. If the host has no matching virtual
environment, use the versioned `qwen4090_local_dev_container_python.sh` launcher with an already
staged exact Python evaluator image ID. The launcher mounts only the deployed source and evidence
read-only, uses host networking for the Tailscale canary, and exposes the Docker socket and GPU
utility only to the bounded preflight process. Omitting the override keeps the repository
`.venv/bin/python` default.

Create one fresh completion state below an existing owner-only mode-`0700` evidence directory:

```bash
infra/llm/qwen4090_candidate_dev_completion.sh prepare \
  EXACT_MATRIX_CANDIDATE_ID \
  /absolute/owner-only/dev-completions/UNIQUE_RUN
```

The outer auxiliary-pause wrapper accepts a no-argument maintenance executable, while the inner
local-Dev runner requires explicit arguments. Use the versioned bridge
`run_qwen4090_candidate_dev_maintenance.sh`; do not create an ad-hoc host wrapper. Configure the
bridge only with absolute owner-controlled paths:

```bash
ALLOW_KHRIN_AUXILIARY_PAUSE=YES \
ALLOW_VLM_MAINTENANCE=YES \
CSIGHT_LOCAL_DEV_PYTHON_BIN=/absolute/deployed-repo/infra/llm/qwen4090_local_dev_container_python.sh \
CSIGHT_LOCAL_DEV_PYTHON_IMAGE_ID=sha256:EXACT_LOCAL_PYTHON_IMAGE_ID \
CSIGHT_IMATRIX_MAINTENANCE_SCRIPT=/absolute/deployed-repo/infra/llm/run_qwen4090_candidate_dev_maintenance.sh \
CSIGHT_VLM_CONTAINER=EXACT_CURRENT_VLM_CONTAINER_NAME \
CSIGHT_EXPECTED_VLM_IMAGE=EXACT_CURRENT_VLM_IMAGE_REFERENCE \
CSIGHT_EXPECTED_VLM_IMAGE_ID=sha256:EXACT_CURRENT_VLM_IMAGE_ID \
CSIGHT_EXPECTED_VLM_CONFIG_HASH=EXACT_64_HEX_COMPOSE_CONFIG_HASH \
CSIGHT_EXPECTED_VLM_MODEL_ID=EXACT_CURRENT_VLM_MODEL_ID \
CSIGHT_QWEN4090_DEV_CANDIDATE_ID=EXACT_MATRIX_CANDIDATE_ID \
CSIGHT_QWEN4090_DEV_RUNTIME_ENV=/absolute/owner-only/candidate-runtime.env \
CSIGHT_QWEN4090_DEV_EVIDENCE_ROOT=/absolute/owner-only/maintenance-evidence \
CSIGHT_QWEN4090_DEV_COMPLETION_STATE=/absolute/owner-only/dev-completions/UNIQUE_RUN \
CSIGHT_QWEN4090_DEV_COMPLETION_TIMEOUT_SECONDS=21600 \
CSIGHT_KHRIN_AUX_EVIDENCE_ROOT=/absolute/owner-only/aux-evidence \
CSIGHT_KHRIN_PAUSE_CONTAINERS='EXACT_NEWLINE_SEPARATED_ALLOWLIST' \
LLAMA_CPP_TOOL_IMAGE_ID=sha256:EXACT_CURRENT_IMAGE_ID \
/absolute/deployed-repo/infra/llm/run_qwen4090_khrin_aux_pause.sh
```

Resolve the exact newline-separated Counsel container set and all five VLM baseline values from
the current healthy containers before launch; placeholders are not valid input and the inner
runner rejects any mismatch before stopping VLM. Do not stop either product stack by hand. The
outer watchdog must be armed before Counsel pauses, and the inner watchdog must be armed before the
VLM stops. A timeout, signal, candidate error, or Mac evaluation error must end in candidate
removal and exact VLM/Counsel restoration.

The launcher writes the successful post-start preflight once as
`local-dev-post-start.json` below the inner maintenance evidence directory, mode `0600`, and prints
its exact path and file digest. Copy that privacy-safe JSON to an owner-only mode-`0600` Mac path
through the authenticated owner SSH session. It binds the semantic matrix digest, artifact bytes,
quantization evidence, recomputed local-Dev identity, runtime image/binary/build/SBOM, Compose
config, inspected container instance, and authenticated canary. It remains Dev-only evidence, not
an artifact revision.

## 4. Run all three live tasks from the Mac

Create one fresh absolute owner-only mode-`0700` result root. While the Khrin sentinel is waiting,
run:

```bash
UV_OFFLINE=1 uv run --frozen --offline python \
  scripts/run_qwen4090_candidate_dev.py run-candidate \
  --candidate-id EXACT_MATRIX_CANDIDATE_ID \
  --matrix evaluation/llm/qwen4090_candidate_matrix_v2.json \
  --evaluation-env /absolute/owner-only/candidate-evaluation.env \
  --result-root /absolute/owner-only/two-candidate-dev-results \
  --expected-source-bundle-digest sha256:RECORDED_SOURCE_DIGEST \
  --expected-lock-digest sha256:RECORDED_LOCK_DIGEST \
  --local-dev-preflight-evidence /absolute/owner-only/local-dev-post-start.json
```

The driver probes the exact model alias before every task and after the final task, then runs
Extraction, Query Builder, and Grounding in that order. A quality-gate failure is retained as valid
Dev evidence and does not skip later tasks. A technical failure stops immediately without retrying
or overwriting partial evidence. Result files are owner-only and contain typed synthetic model
outputs, hashes, aggregate/scored observations, bounded error codes, and no raw provider response,
provider request ID, or real customer data.

After `QWEN4090_CANDIDATE_DEV_COMPLETE`, use the printed execution-manifest digest to release the
remote sentinel:

```bash
infra/llm/qwen4090_candidate_dev_completion.sh complete \
  EXACT_MATRIX_CANDIDATE_ID \
  /absolute/owner-only/dev-completions/UNIQUE_RUN \
  COMPLETE \
  sha256:CANDIDATE_EXECUTION_MANIFEST_DIGEST
```

Run that command on Khrin through the authenticated owner SSH session. The waiting maintenance
process then exits normally and must report exact VLM and Counsel restoration. If the Mac driver
exits with a technical failure, it writes `candidate_dev_failure.json` and prints that file's
`manifest_digest`. Signal the normal failure path instead of abandoning the owner process:

```bash
infra/llm/qwen4090_candidate_dev_completion.sh complete \
  EXACT_MATRIX_CANDIDATE_ID \
  /absolute/owner-only/dev-completions/UNIQUE_RUN \
  FAILED \
  sha256:CANDIDATE_DEV_FAILURE_MANIFEST_DIGEST
```

The sentinel wait exits nonzero and both nested traps restore their baselines. Owner loss or manual
interrupt is an emergency fallback only when the Mac driver fails before it can emit bounded
failure evidence. Preserve the private failure package and use a new result root for a retry.

Repeat sections 2–4 for the second candidate only after the first candidate and original services
are fully restored.

## 5. Select the Dev winner

After both candidate execution manifests exist below the same result root, run:

```bash
UV_OFFLINE=1 uv run --frozen --offline python \
  scripts/run_qwen4090_candidate_dev.py select-winner \
  --matrix evaluation/llm/qwen4090_candidate_matrix_v2.json \
  --result-root /absolute/owner-only/two-candidate-dev-results \
  --expected-source-bundle-digest sha256:RECORDED_SOURCE_DIGEST \
  --expected-lock-digest sha256:RECORDED_LOCK_DIGEST
```

Selection recomputes every metric and score binding from the typed Dev observations. It first
requires every absolute Extraction, Query Builder, Grounding, and injection-safety gate. If only
one passes, that candidate wins. If both pass, the frozen maximin/tie-break rule applies. If neither
passes, the immutable decision is `NO_WINNER`. No Test evidence participates.

Only a separately published, signed, organization-controlled artifact may later freeze the winning
Dev profile and request the one-time sealed Test. This runbook never performs that promotion.

## 6. Recover a failed Extraction prompt before considering QLoRA

When Extraction fails mainly on structured output, diagnose the inference contract before training.
The adapter records only stable categories such as invalid JSON, truncation, missing field, invalid
enum, extra field, schema constraint, and exact-source-quote mismatch. Do not retain provider text,
field paths, request IDs, or customer content in the diagnosis package.

Use `scripts/screen_qwen4090_extraction_prompts.py` only inside the same protected Khrin maintenance
window described above. The default `canary20` scope compares production `2.0.0` with the existing
Dev-only `2.0.0-local.2` prompt on a fixed 20-record synthetic Dev subset:

```bash
python scripts/screen_qwen4090_extraction_prompts.py \
  --scope canary20 \
  --candidate-id EXACT_MATRIX_CANDIDATE_ID \
  --matrix evaluation/llm/qwen4090_candidate_matrix_v2.json \
  --env-file /absolute/owner-only/candidate-evaluation.env \
  --output /absolute/fresh-owner-only/prompt-canary.json
```

Only after the canary improves structure without a forbidden-field, prompt-injection, or reasoning
leakage regression may `full-dev-local2` run all 120 synthetic Dev records. That scope evaluates
`local.2` alone and still cannot freeze, open Test, publish a model, or change a Core route.

```bash
python scripts/screen_qwen4090_extraction_prompts.py \
  --scope full-dev-local2 \
  --candidate-id EXACT_MATRIX_CANDIDATE_ID \
  --matrix evaluation/llm/qwen4090_candidate_matrix_v2.json \
  --env-file /absolute/owner-only/candidate-evaluation.env \
  --output /absolute/fresh-owner-only/local2-full-dev.json
```

Signal the completion manifest digest to the remote sentinel and verify exact VLM/Counsel restoration
and zero candidate leftovers after each scope. A better prompt screen is not an Extraction gate pass.
If full Dev still fails, change only the observed failure dimensions and repeat a fresh canary. Start
QLoRA only after prompt/schema/runtime experiments stop improving the frozen Dev metrics.

### Observed Q5 prompt recovery on 2026-09-01

The later Dev-only scopes `canary-local4`, `canary-local5`, `canary-local6`, and
`full-dev-local5` compare or evaluate prompts that are deliberately absent from
`PRODUCT_DEFECT_PROMPT_REGISTRY`. They retain the same synthetic Dev split and cannot select a
runtime prompt, create a qualification decision, or open Test.

- `local.4` improved the 20-record ambiguity F1 from `0.222222` to `0.869565`, but regressed
  requested-action F1 to `0.857143` and p95 latency to `6,203.244 ms`; it was not scaled up.
- `local.5` kept 20/20 structure and exact quotes, reached requested-action F1 `1.0`, ambiguity F1
  `0.666667`, and zero safety violations. Its p95 was `5,070.952 ms`, only marginally above the
  absolute full-Dev budget, so one compact confirmation candidate was permitted before scaling.
- `local.6` also kept 20/20 structure, exact quotes, action F1 `1.0`, and zero safety violations,
  but ambiguity F1 fell to `0.516129` and p95 remained `5,017.840 ms`; it was rejected.
- The less over-compressed `local.5` was therefore evaluated once on all 120 Dev records. It
  achieved 120/120 structure and exact quotes, issue F1 `1.0`, requested-action F1 `0.976744`,
  system-missing accuracy `1.0`, action consistency `0.966667`, ambiguity F1 `0.697674`, and zero
  injection, reasoning-leakage, or forbidden-field violations at `40.808092 tok/s`.
- `local.5` is still not qualified: ambiguity F1 misses the `0.7` floor and p95 `5,084.207 ms`
  misses the `5,000 ms` ceiling. It must remain Dev-only and unregistered. Do not freeze or open
  sealed Test from this evidence.

This result is close enough that QLoRA is not yet the automatic next step. First add PII-free
aggregate ambiguity confusion counts and test a deterministic ambiguity-validation/runtime-latency
correction on a fresh canary. Begin Extraction QLoRA only if those bounded changes cannot close the
remaining two gates without regressing exact quotes, actions, or safety.

### Observed Q5 Extraction Dev gate closure on 2026-09-01

The bounded follow-up kept the model, Q5 artifact, synthetic Dev split, llama.cpp runtime, and typed
Extraction schema fixed. It added only privacy-safe aggregate diagnostics and a versioned Dev-only
ambiguity guard. The guard is not registered in the product runtime and does not authorize Test,
freeze, route activation, or a release.

- `diagnose-local5` recorded ambiguity confusion without retaining source text or predictions:
  `TP=10`, `FP=8`, `FN=2`. False positives were concentrated in location, vague-description, and
  contradiction labels. Provider p95 was `5,111 ms`, while adapter overhead p95 was only
  `5.184 ms`, so the residual latency was provider-side rather than post-processing overhead.
- `local.7` was a compact prompt experiment. Although p95 improved to `4,646.459 ms`, issue F1,
  action F1, and guarded ambiguity F1 regressed to `0.75`, `0.888889`, and `0.514286`; it was
  rejected after the 20-record canary.
- `local.8` preserved the successful `local.5` contract and only constrained the summary to one
  factual sentence of at most 120 characters. With ambiguity guard
  `product_defect_ambiguity_guard/1.0.0-dev`, its 20-record canary reached 20/20 structure and exact
  quotes, issue/action/ambiguity F1 `1.0`, p95 `4,801.166 ms`, and zero safety violations.
- The guarded `local.8` was then evaluated once on all 120 Dev records. It reached 120/120 structure,
  Pydantic validity, and exact quotes; issue F1 `0.987448`; action F1 `0.976744`; system-missing
  accuracy `1.0`; action consistency `0.966667`; ambiguity F1 `1.0` with `TP=72`, `FP=0`, `FN=0`;
  p95 `4,908.237 ms`; and `40.432121 tok/s`. Injection, reasoning-leakage, and forbidden-field
  violations were all zero.
- The owner-only full-Dev report SHA-256 is
  `2612cbed45f6f6b5346bd5a78cecb1161a616a918b4674388ae184648470b14a`; its scoring-profile
  digest is `sha256:b6ea1403d732752cd8b35a220a86dd2a6b7f025ffb05fab43340800ecd3ad882`.
  Re-evaluation through the canonical Extraction gate passed all 15 checks and produced gate digest
  `sha256:6f5cfb9725b47fd757e38d5b3c1062c2e123ad0eb45bb9f70d69b4ac1ef336fa`.

This closes only the Q5 **Extraction synthetic-Dev gate**. `local.8` and the guard remain
unregistered Dev candidates. Query Builder and Grounding still fail their absolute Dev gates, so
the candidate remains `NO_WINNER`/`NO_RELEASE_ELIGIBLE`; sealed Test must remain unopened. Before
the guard can become a product runtime component, bind its version and content hash into the signed
runtime identity and record that decision in an ADR, then rerun a fresh all-three-task Dev gate.

### Observed Q5 Grounding Dev gate closure on 2026-09-01

The Grounding follow-up reused the already versioned runtime prompt `1.1.0-local.2`; it did not add
a new prompt or alter the model, Q5 artifact, schema, dataset, llama.cpp runtime, or safety gate.
The screen retained only aggregate metrics, prompt/profile identity, failure counts, and result
digests. It cannot open Test, freeze, activate, publish, or route Core traffic.

- The production-profile failure was isolated before another live run. Q5 `1.1.0` had 39/40 valid
  normal outputs, required-fact coverage `0.95`, unresolved-condition recall `0.0`, and deterministic
  replay `0.975`. All 20 attack outputs were structurally valid, but five outputs repeated unsafe
  terms while rejecting the instruction, producing injection violation `0.25`.
- The fixed canary contained 12 normal Grounding records plus one record from each of eight attack
  categories. `local.2` passed every absolute check: 12/12 normal, 8/8 attack, citation/fact/
  unresolved/replay metrics `1.0`, and every safety violation `0`. Report SHA-256:
  `e752095d635069eeab7713828728c59fa47441e45956211ff5eeee72c5d7b3b7`.
- The same prompt was then run once on the complete synthetic Dev split: 40 normal records, each
  with a second deterministic replay, plus 20 attack records. All 25 canonical Grounding checks
  passed. Structure, Pydantic validity, citation validity/precision/recall/completeness, required
  fact coverage, unresolved-condition recall, and deterministic replay were all `1.0`; allowlist,
  unknown/wrong/cross-tenant/duplicate citation, forbidden claim/field, overstatement, injection,
  and reasoning leakage rates were all `0`.
- Normal end-to-end latency was p50 `7,877.527 ms` and p95 `7,985.891 ms`, including both replay
  calls. Attack latency was p50 `3,427.051 ms` and p95 `3,517.389 ms`. The full-Dev report SHA-256 is
  `a36f38815052cd22274a718eb8daa292841cde84d645058b7bdbfc0c03d540cf`; prompt hash
  `e375f153be637bd674fa620e9452d2e55161ff29cbb35843e2b3ae7aefa52297`; profile digest
  `sha256:2f862cfa509831b0c3b73bc609b71587d8346088702e8111c2dde00c05495515`.

This closes only the Q5 **Grounding synthetic-Dev gate**. Extraction and Grounding now pass their
task gates, but the LLM Query Builder still does not beat the frozen RAW→HYBRID retrieval baseline.
The overall candidate therefore remains `NO_WINNER`/`NO_RELEASE_ELIGIBLE`; do not open sealed Test
until one fresh, jointly bound three-task Dev run passes with the final prompt/runtime identities.
