# ADR-0125: CSight-owned GGUF quantization and llama.cpp remain Shadow-only until qualified

- Status: Accepted
- Date: 2026-08-31

## Context

The existing RTX 4090 candidates use vLLM and either a Community 27B W4A16 package or the official
8B FP8 package. Both loaded successfully, but neither passed the absolute Extraction quality and
safety gates. Startup, a healthy endpoint, or a model-name canary therefore cannot establish release
eligibility. The single RTX 4090 also already hosts a separate demo VLM, so an unguarded candidate
run could disrupt the known-good demonstration path.

CSight needs one reproducible 27B text runtime for Extraction, LLM Query Builder, and Grounded
Explanation. The quantization calibration must represent those tasks without incorporating raw
customer inquiries or direct identifiers, and the resulting package must remain advisory in both
PRIMARY and SHADOW execution modes.

## Decision

1. The source is `Qwen3.8-27B-BF16.gguf` from the exact
   `ggml-org/Qwen3.8-27B-GGUF` revision, whose declared upstream is the exact official
   `Qwen/Qwen3.8-27B` revision. Both repository revisions, the BF16 byte size, and its Hugging Face
   LFS SHA-256 digest are verified before quantization. Quantized, AWQ, FP8, MTP, and multimodal
   projection files are not accepted as quantization sources for this text runtime.
2. Conversion inspection, importance-matrix generation, quantization, benchmarking, and serving use
   one pinned llama.cpp commit and one digest-pinned CUDA build image. Host package installation and
   floating `latest` tags are prohibited. The binary digest, build flags, dependency manifest, and
   SBOM are release evidence.
3. The Dev-only calibration mixture contains synthetic CSight Extraction, Query Builder, Grounding,
   strict-JSON, and injection examples plus pinned public Korean and English text. It excludes every
   sealed Test record, raw inquiry, direct personal identifier, and customer image. Only the corpus
   manifest, source attribution, counts, and content digests may accompany the model artifact.
   Public rows require a `public_dataset_fixture_attestation/1.0.0` sidecar created while reading the
   HTTPS Dataset Viewer response. The sidecar binds the exact repository revision, config, split,
   pagination query, returned `x-revision`, received response-body digest, and canonical row payload
   digest. Offline replay recomputes the fixture, page, and query digests; a fixture without its
   matching sidecar fails before normalization. Source-preparation output directories and public
   capture directories are owner-only (`0700`), and every emitted plan, corpus input, fixture,
   sidecar, and manifest is created without overwrite at mode `0600`.
4. The controlled comparison contains a no-imatrix Q4_K_M control, an imatrix Q4_K_M candidate, a
   selectively protected mixed Q4/Q6 candidate, and an imatrix Q5_K_S quality ceiling. All originate
   from the same BF16 file and use the same prompt, schema, context, and runtime. Q3 and lower-bit
   candidates are outside this qualification.
   After that comparison has selected the mixed Q4/Q6 and Q5 candidates, a changed pinned tool image
   may regenerate only those two candidates under the additive
   `DEV_QUALIFICATION_PAIR` run-plan contract. The pair must use a new owner-only output namespace,
   the new clean importance matrix, and the exact new quantizer digest. It does not rewrite or inherit
   the earlier four-way evidence and remains limited to canary and Dev selection until separately
   qualified.
5. Candidate-matrix v1 and its vLLM evidence remain historical. Candidate-matrix v2 adds runtime
   kind, GGUF identity, source and recipe digests, llama.cpp identity, serving profile, and task-level
   qualification evidence. A v2 tool must not reinterpret or rewrite v1 evidence.
6. Release-manifest v1.1 is an additive union with v1.0. It records GGUF and llama.cpp provenance and
   distinguishes `SHADOW_CANDIDATE` from `RELEASE_ELIGIBLE`. A Shadow candidate may be activated only
   in `SHADOW`; attempting to activate it in `PRIMARY` fails before an activation event is written.
7. A personal private artifact repository is acceptable for qualification and Shadow evidence only.
   PRIMARY eligibility additionally requires the exact content to be mirrored into an organization-
   controlled private namespace and referenced by a newly signed immutable manifest.
8. `LlamaCppLLMProvider` is an external adapter behind the existing LLM port. Extraction, Query
   Builder, and Grounding share one GGUF and runtime but retain separate signed task manifests,
   prompts, schemas, route plans, and evaluation digests. RAW and DETERMINISTIC query strategies do
   not resolve a model route or call the provider.
9. The target serving profile is text-only, context 4096, concurrency 1, deterministic non-thinking
   generation, full GPU offload, flash attention, Q8_0 K/V cache, offline artifact access, no Web UI,
   authenticated Tailscale-only exposure, and at least 2 GiB observed free VRAM.
10. Candidate comparison occurs on Dev only. One selected candidate and frozen task profiles may open
    sealed Test once. Registration and Shadow activation require all task safety, semantic quality,
    latency, throughput, soak, metadata, and hardware gates. Release eligibility additionally
    requires 100 terminal full-pipeline Shadow cases and 20 terminal workflow/fault cases with zero
    policy decisions, human decisions, resolutions, or external actions created by Shadow.
11. Every GPU maintenance run records the running VLM identity and a working health response before
    stopping it, installs an unconditional restore trap, runs one candidate, and restores and
    health-checks the original VLM. Access, provenance, memory, candidate, or restoration failure
    stops the qualification; it never triggers another model as an automatic fallback.

## Consequences

- A locally generated GGUF can be reproducible without weakening the existing signed route and human
  decision boundaries.
- The same model bytes cannot inherit another candidate's prompt, runtime, or evaluation result.
- Personal artifact custody can produce useful Shadow evidence but cannot be represented as a B2B
  release-ready supply chain.
- If no candidate passes, the correct result remains `NO_RELEASE_ELIGIBLE`; the existing VLM and
  Core demo path are restored without modification.
- Source-preparation manifest v1.0 assets created before public-response attestations remain useful
  development evidence but are not quantization-qualification evidence. Migration is additive:
  recapture the two pinned public sources online, preserve the emitted fixture/sidecar pairs locally,
  and rebuild the corpus under source-preparation manifest v1.1. Existing corpus bytes are not
  silently reclassified or overwritten.
- This decision extends ADR-0113 and ADR-0122. It does not replace their append-only activation,
  exact runtime identity, fail-closed execution, or no-cross-model-fallback requirements.

## Related decisions

- [ADR-0103](0103-limited-pilot-execution-isolation-and-shadow-mode.md)
- [ADR-0113](0113-rtx4090-qwen-candidate-release-gate.md)
- [ADR-0122](0122-append-only-task-model-route-plans.md)
- [ADR-0123](0123-query-grounding-route-snapshots-and-pilot-readiness.md)
