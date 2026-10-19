SHELL := /bin/sh

UV ?= uv
COMPOSE ?= docker compose
COMPOSE_FILE := infra/compose.core.yml
COMPOSE_RLS_FILE := infra/compose.rls.yml
ENV_FILE ?= .env
PILOT_ENV_FILE ?= infra/pilot/.env.pilot
COMPOSE_CMD := $(COMPOSE) --env-file $(ENV_FILE) -f $(COMPOSE_FILE)
COMPOSE_RLS_CMD := $(COMPOSE_CMD) -f $(COMPOSE_RLS_FILE)
EMBEDDING_PORT ?= 8091
EMBEDDING_BASE_URL ?= http://127.0.0.1:$(EMBEDDING_PORT)
EMBEDDING_PID_FILE ?= .embedding-service.pid
RERANKER_PORT ?= 8092
RERANKER_BASE_URL ?= http://127.0.0.1:$(RERANKER_PORT)
RERANKER_PID_FILE ?= .reranker-service.pid
RERANKER_DOWNLOAD_SECONDS ?= 0
RERANKER_COLD_LOAD_SECONDS ?= 0
POLICY_TENANT ?= csight-demo-brand
POLICY_INDEX_VERSION ?= 1.0.0
CSIGHT_POLICY_OUTPUT ?= local-data/csight-synthetic-policy-runtime-v2.0.1
E3_TOP100_PACKAGE ?=
E3_TOP100_OUTPUT ?= local-data/e3-top100-replay/replay_report.json
E3_TOP100_CORE_SAMPLE_SIZE ?= 6
REALISTIC_DEMO_TOP100_SOURCE ?=
REALISTIC_DEMO_NORMAL_SOURCE ?=
REALISTIC_DEMO_OUTPUT ?= local-data/realistic-internal-demo-v1/seed_report.json
REALISTIC_DEMO_ACTOR_EMAIL ?= csight@csight.demo
REALISTIC_DEMO_V2_MANIFEST ?= evaluation/realistic_internal_demo_v2/manifest.json
REALISTIC_DEMO_V3_MANIFEST ?= evaluation/realistic_internal_demo_v3/manifest.json
QWEN4090_CANDIDATE_ID ?=
QWEN4090_ENV_FILE ?= .env
QWEN4090_RUNTIME_ENV_FILE ?= infra/llm/.env.llm
EVALUATION_OUTPUT_DIR ?=
EVALUATION_OUTPUT_ARGS = $(if $(strip $(EVALUATION_OUTPUT_DIR)),--output-dir "$(EVALUATION_OUTPUT_DIR)",$(error Set EVALUATION_OUTPUT_DIR to a new run directory))

.DEFAULT_GOAL := help

.PHONY: help up up-rls provision-runtime-logins down logs migrate seed outbox retention-once retention-start retention-stop lint format-check typecheck test test-integration test-all test-analysis test-analysis-integration test-external-llm test-external-vision test-external-embedding test-external-reranker test-local-llm web-lint web-typecheck web-openapi web-test web-build web-e2e qualify-oidc-keycloak qualify-evidence-security qualify-observability qualify-restore-drill qualify-load-isolation smoke-analysis build-policy-corpus validate-policy-corpus build-policy-rules validate-policy-rules ingest-policy-rules validate-policy-rule-db evaluate-policy-engine smoke-policy-evaluation build-human-review-evaluation validate-human-review-evaluation evaluate-human-review-workflow smoke-human-review inspect-human-review-queue verify-poc-readiness require-limited-poc verify-scenario-poc up-scenario-poc seed-scenario-poc-demo smoke-scenario-vision demo-scenario-poc build-evaluation-data validate-evaluation-data evaluate-extraction-v2 evaluate-extraction-v2-qwen freeze-extraction-v2-qwen evaluate-extraction-v2-qwen-test verify-qwen4090-candidates verify-qwen4090-compose-profiles collect-qwen4090-host-evidence verify-qwen4090-host start-qwen4090-candidate stop-qwen4090-candidate require-qwen4090-release report-reference-data ingest-policy-corpus validate-policy-db start-embedding stop-embedding health-embedding build-policy-embeddings activate-policy-index list-policy-indexes seed-policy-identities evaluate-policy-lexical evaluate-policy-dense evaluate-policy-hybrid evaluate-policy-retrieval smoke-policy-search analyze-policy-candidates evaluate-policy-candidate-upper-bound start-reranker stop-reranker health-reranker qualify-policy-reranker activate-policy-reranker-profile evaluate-policy-reranker-dev evaluate-policy-reranker-test smoke-policy-reranked-search build-query-builder-dataset validate-query-builder-dataset evaluate-query-builder-raw evaluate-query-builder-deterministic evaluate-query-builder-llm evaluate-query-builder smoke-policy-retrieval-run evaluate-grounding-contract smoke-grounded-explanation setup-local-llm start-local-llm stop-local-llm health-local-llm qualify-local-llm evaluate-local-extraction evaluate-local-query-builder evaluate-local-grounding evaluate-local-llm-all smoke-local-llm-e2e setup-vision-e3 start-vision-e3 stop-vision-e3 health-vision-e3 qualify-vision-e3 test-vision-e3 up-e3-scenario-poc smoke-e3-scenario-vision replay-e3-top100 seed-realistic-poc-demo seed-realistic-poc-demo-v2 seed-realistic-poc-demo-v3
.PHONY: prepare-csight-policy-runtime
.PHONY: audit-qwen4090-hub
.PHONY: pilot-config pilot-preflight pilot-up pilot-status pilot-stop

help:
	@echo "CSight Core commands"
	@echo "  make up            Build and start the core environment"
	@echo "  make provision-runtime-logins  Create/rotate strict DB logins from private files"
	@echo "  make up-rls        Start Core with distinct non-bypass runtime DB logins"
	@echo "  make down          Stop the core environment (preserves volumes)"
	@echo "  make logs          Follow core service logs"
	@echo "  make migrate       Apply Alembic migrations in the app image"
	@echo "  make seed          Explicitly seed local/test identities after migration"
	@echo "  make outbox        Dispatch one batch of pending analysis events"
	@echo "  make retention-once  Run one bounded automatic retention sweep"
	@echo "  make retention-start/retention-stop  Control the opt-in pilot retention scheduler"
	@echo "  make pilot-preflight/pilot-up/pilot-status/pilot-stop  Control the fail-closed pilot profile"
	@echo "  make lint          Run Ruff lint checks"
	@echo "  make format-check  Check Ruff formatting"
	@echo "  make typecheck     Run Pyright"
	@echo "  make test          Run CI-safe tests (no local infra or external GPU)"
	@echo "  make test-integration  Run integration tests against the core environment"
	@echo "  make test-all      Run CI-safe and core integration tests"
	@echo "  make web-lint web-typecheck web-openapi web-test web-build web-e2e  Verify the consultant console"
	@echo "  make qualify-oidc-keycloak  Run isolated real-Keycloak PKCE and revocation gates"
	@echo "  make qualify-evidence-security  Run isolated ClamAV HTTP upload and outage gates"
	@echo "  make qualify-observability  Run isolated OTLP, metric query, and local alert gates"
	@echo "  make qualify-restore-drill  Run isolated PostgreSQL WAL and MinIO version restore gates"
	@echo "  make qualify-load-isolation  Run 20-client reads and synthetic queue isolation gates"
	@echo "  make test-analysis Run CI-safe analysis-focused tests"
	@echo "  make test-analysis-integration  Run analysis integration tests"
	@echo "  make test-external-llm  Opt in to the configured external vLLM test"
	@echo "  make test-external-vision  Opt in to the configured external Vision test"
	@echo "  make smoke-analysis  Run the authenticated Mock analysis smoke flow"
	@echo "  make build-policy-corpus  Build clause-based synthetic policy reference outputs"
	@echo "  make validate-policy-corpus  Validate corpus metadata, versions, parents, and coverage"
	@echo "  make build-evaluation-data  Build all synthetic gold datasets and manifests"
	@echo "  make validate-evaluation-data  Validate counts, references, splits, and tenant isolation"
	@echo "  make evaluate-extraction-v2  Run the reference gold self-check (not an external model eval)"
	@echo "  make evaluate-extraction-v2-qwen QWEN4090_CANDIDATE_ID=...  Run Qwen v2 Dev"
	@echo "  make freeze-extraction-v2-qwen QWEN4090_CANDIDATE_ID=...  Freeze passing Dev"
	@echo "  make evaluate-extraction-v2-qwen-test QWEN4090_CANDIDATE_ID=...  Run sealed Test once"
	@echo "  make verify-qwen4090-candidates  Validate and report the frozen RTX 4090 candidate gate"
	@echo "  make audit-qwen4090-hub  Verify exact Hub revisions, lineage, license, and weight bytes"
	@echo "  make verify-qwen4090-compose-profiles  Check runnable Shadow profiles against matrix"
	@echo "  make collect-qwen4090-host-evidence QWEN4090_CANDIDATE_ID=...  Collect unpinned host evidence"
	@echo "  make verify-qwen4090-host QWEN4090_CANDIDATE_ID=...  Require exact pinned host evidence"
	@echo "  make start-qwen4090-candidate QWEN4090_CANDIDATE_ID=...  Start one Shadow candidate"
	@echo "  make stop-qwen4090-candidate  Stop candidate runtime and preserve model cache"
	@echo "  make require-qwen4090-release  Fail unless one RTX 4090 candidate is release eligible"
	@echo "  make build-query-builder-dataset / validate-query-builder-dataset"
	@echo "  make evaluate-query-builder  Compare frozen-HYBRID query strategies"
	@echo "  make evaluate-grounding-contract  Qualify deterministic citation guardrails"
	@echo "  make smoke-grounded-explanation  Run authenticated Mock grounding smoke"
	@echo "  make report-reference-data  Generate aggregate JSON and Markdown quality reports"
	@echo "  make ingest-policy-corpus  Explicitly ingest the validated synthetic corpus"
	@echo "  make validate-policy-db  Verify corpus, embedding, and active-index invariants"
	@echo "  make build-policy-rules / validate-policy-rules  Build and validate typed rules"
	@echo "  make ingest-policy-rules / validate-policy-rule-db  Persist and audit rules"
	@echo "  make evaluate-policy-engine  Run Dev and sealed Test deterministic evaluation"
	@echo "  make smoke-policy-evaluation  Run authenticated asynchronous policy smoke"
	@echo "  make build-human-review-evaluation / validate-human-review-evaluation"
	@echo "  make evaluate-human-review-workflow  Re-evaluate Dev and verify sealed artifacts"
	@echo "  make smoke-human-review / inspect-human-review-queue  Verify local review runtime"
	@echo "  make verify-poc-readiness  Report the evidence-backed PoC promotion verdict"
	@echo "  make require-limited-poc  Fail unless every Limited PoC gate is evidenced"
	@echo "  make verify-scenario-poc  Verify the sealed synthetic scenario PoC pack"
	@echo "  make demo-scenario-poc  Build, seed, and smoke the local binary-Vision scenario demo"
	@echo "  make start-embedding  Start the private host-native Qwen embedding service"
	@echo "  make stop-embedding  Stop the private embedding service started by Make"
	@echo "  make health-embedding  Probe embedding health and pinned model metadata"
	@echo "  make build-policy-embeddings  Build/reuse embeddings and activate complete indexes"
	@echo "  make prepare-csight-policy-runtime  Preserve v1 and activate fictional Commerce policy v2"
	@echo "  make activate-policy-index POLICY_TENANT=... POLICY_INDEX_VERSION=..."
	@echo "  make list-policy-indexes  List versioned policy indexes"
	@echo "  make evaluate-policy-{lexical,dense,hybrid,retrieval}  Verify locked results"
	@echo "  make smoke-policy-search  Run two-tenant authenticated retrieval smoke"
	@echo "  make analyze-policy-candidates  Measure/freeze Dev candidate K then diagnose Test once"
	@echo "  make start-reranker / stop-reranker / health-reranker"
	@echo "  make qualify-policy-reranker  Measure the running pinned reranker"
	@echo "  make activate-policy-reranker-profile  Persist the locked ACTIVE execution profile"
	@echo "  make evaluate-policy-reranker-{dev,test}  Run the locked reranker evaluation"
	@echo "  make smoke-policy-reranked-search  Run two-tenant HYBRID_RERANKED smoke"
	@echo "  make setup-local-llm / start-local-llm / stop-local-llm / health-local-llm"
	@echo "  make test-local-llm / qualify-local-llm  Opt in to the host-native MLX service"
	@echo "  make evaluate-local-{extraction,query-builder,grounding}  Run Local MLX Dev"
	@echo "  make evaluate-local-llm-all  Run all Local MLX Dev evaluations"
	@echo "  make smoke-local-llm-e2e  Run the Local MLX PoC smoke path"
	@echo "  make setup-vision-e3 / start-vision-e3 / stop-vision-e3 / health-vision-e3"
	@echo "  make qualify-vision-e3  Run a real E3 HTTP forward on a synthetic image"
	@echo "  make up-e3-scenario-poc / smoke-e3-scenario-vision  Run E3 through Core"
	@echo "  make replay-e3-top100 E3_TOP100_PACKAGE=...  Replay selected positives through E3/Core"
	@echo "  make seed-realistic-poc-demo ...  Reproduce the preserved v1 customer-case demo"
	@echo "  make seed-realistic-poc-demo-v2 ...  Seed the long-inquiry ecommerce demo"
	@echo "  make seed-realistic-poc-demo-v3 ...  Add ten closed-set ecommerce demo cases"

up:
	$(COMPOSE_CMD) up --build --detach --wait --remove-orphans

provision-runtime-logins:
	$(UV) run python scripts/provision_postgres_runtime_logins.py

up-rls:
	$(COMPOSE_RLS_CMD) up --build --detach --wait --remove-orphans

down:
	$(COMPOSE_CMD) down --remove-orphans

logs:
	$(COMPOSE_CMD) logs --follow --tail=200

migrate:
	$(COMPOSE_CMD) run --rm migrator

seed:
	$(UV) run python -m app.bootstrap.seed --env-file $(ENV_FILE)

qualify-evidence-security:
	./scripts/qualify_evidence_security.sh

qualify-observability:
	$(UV) run python scripts/qualify_observability.py

qualify-restore-drill:
	$(UV) run python scripts/qualify_restore_drill.py

qualify-load-isolation:
	$(UV) run python scripts/qualify_load_isolation.py

outbox:
	$(COMPOSE_CMD) run --rm dispatcher uv run python -m app.interface.dispatchers.outbox --once

retention-once:
	$(COMPOSE_RLS_CMD) --profile pilot-maintenance run --rm privacy-lifecycle \
		uv run python -m app.interface.maintenance.privacy_lifecycle --once

retention-start:
	$(COMPOSE_RLS_CMD) --profile pilot-maintenance up --detach --wait privacy-lifecycle

retention-stop:
	$(COMPOSE_RLS_CMD) --profile pilot-maintenance stop privacy-lifecycle

pilot-config:
	CSIGHT_PILOT_ENV_FILE="$(PILOT_ENV_FILE)" ./scripts/csight_pilot_control.sh config

pilot-preflight:
	CSIGHT_PILOT_ENV_FILE="$(PILOT_ENV_FILE)" ./scripts/csight_pilot_control.sh preflight

pilot-up:
	CSIGHT_PILOT_ENV_FILE="$(PILOT_ENV_FILE)" ./scripts/csight_pilot_control.sh start

pilot-status:
	CSIGHT_PILOT_ENV_FILE="$(PILOT_ENV_FILE)" ./scripts/csight_pilot_control.sh status

pilot-stop:
	CSIGHT_PILOT_ENV_FILE="$(PILOT_ENV_FILE)" ./scripts/csight_pilot_control.sh stop

lint:
	$(UV) run ruff check .

format-check:
	$(UV) run ruff format --check app tests alembic scripts infra

typecheck:
	$(UV) run pyright

test:
	$(UV) run pytest -q -m "not integration and not external_gpu and not external_vision and not external_embedding and not external_reranker and not external_local_llm"

test-integration:
	$(UV) run python scripts/run_integration_tests.py

test-all: test test-integration

web-lint:
	npm --prefix web run lint

web-typecheck:
	npm --prefix web run typecheck

web-openapi:
	npm --prefix web run check:api

web-test:
	npm --prefix web test

web-build:
	npm --prefix web run build

web-e2e:
	npm --prefix web run test:e2e

qualify-oidc-keycloak:
	./scripts/qualify_oidc_keycloak.sh

test-analysis:
	$(UV) run pytest -q -m "not integration and not external_gpu" -k "analysis or outbox or vllm or text_extraction"

test-analysis-integration:
	$(UV) run python scripts/run_integration_tests.py -- -k "analysis or outbox or vllm or text_extraction"

test-external-llm:
	RUN_EXTERNAL_GPU_TESTS=1 $(UV) run pytest -q -m external_gpu

test-external-vision:
	RUN_EXTERNAL_VISION_TESTS=1 $(UV) run pytest -q -m external_vision

setup-vision-e3:
	./infra/vision_e3/setup_vision_e3.sh

start-vision-e3:
	./infra/vision_e3/serve_vision_e3.sh

stop-vision-e3:
	$(UV) run python infra/vision_e3/stop_vision_e3.py

health-vision-e3:
	./infra/vision_e3/healthcheck.sh

qualify-vision-e3:
	.venv-vision-e3/bin/python infra/vision_e3/qualify_vision_e3.py

test-vision-e3:
	PYTHONPATH=. .venv-vision-e3/bin/python -m pytest -q infra/vision_e3/tests

replay-e3-top100:
	@test -n "$(E3_TOP100_PACKAGE)" || (echo "E3_TOP100_PACKAGE is required" >&2; exit 2)
	$(UV) run python scripts/evaluate_e3_top100_replay.py \
		--package "$(E3_TOP100_PACKAGE)" \
		--output "$(E3_TOP100_OUTPUT)" \
		--core-sample-size "$(E3_TOP100_CORE_SAMPLE_SIZE)" \
		--env-file "$(ENV_FILE)"

seed-realistic-poc-demo:
	@test -n "$(REALISTIC_DEMO_TOP100_SOURCE)" || (echo "REALISTIC_DEMO_TOP100_SOURCE is required" >&2; exit 2)
	@test -n "$(REALISTIC_DEMO_NORMAL_SOURCE)" || (echo "REALISTIC_DEMO_NORMAL_SOURCE is required" >&2; exit 2)
	$(UV) run python scripts/seed_realistic_poc_demo.py \
		--top100-source "$(REALISTIC_DEMO_TOP100_SOURCE)" \
		--normal-source "$(REALISTIC_DEMO_NORMAL_SOURCE)" \
		--output "$(REALISTIC_DEMO_OUTPUT)" \
		--actor-email "$(REALISTIC_DEMO_ACTOR_EMAIL)" \
		--env-file "$(ENV_FILE)"

seed-realistic-poc-demo-v2:
	@test -n "$(REALISTIC_DEMO_TOP100_SOURCE)" || (echo "REALISTIC_DEMO_TOP100_SOURCE is required" >&2; exit 2)
	@test -n "$(REALISTIC_DEMO_NORMAL_SOURCE)" || (echo "REALISTIC_DEMO_NORMAL_SOURCE is required" >&2; exit 2)
	$(UV) run python scripts/seed_realistic_poc_demo.py \
		--top100-source "$(REALISTIC_DEMO_TOP100_SOURCE)" \
		--normal-source "$(REALISTIC_DEMO_NORMAL_SOURCE)" \
		--manifest "$(REALISTIC_DEMO_V2_MANIFEST)" \
		--actor-email "$(REALISTIC_DEMO_ACTOR_EMAIL)" \
		--env-file "$(ENV_FILE)"

seed-realistic-poc-demo-v3:
	@test -n "$(REALISTIC_DEMO_TOP100_SOURCE)" || (echo "REALISTIC_DEMO_TOP100_SOURCE is required" >&2; exit 2)
	@test -n "$(REALISTIC_DEMO_NORMAL_SOURCE)" || (echo "REALISTIC_DEMO_NORMAL_SOURCE is required" >&2; exit 2)
	$(UV) run python scripts/seed_realistic_poc_demo.py \
		--top100-source "$(REALISTIC_DEMO_TOP100_SOURCE)" \
		--normal-source "$(REALISTIC_DEMO_NORMAL_SOURCE)" \
		--manifest "$(REALISTIC_DEMO_V3_MANIFEST)" \
		--actor-email "$(REALISTIC_DEMO_ACTOR_EMAIL)" \
		--env-file "$(ENV_FILE)"

test-external-embedding:
	RUN_EXTERNAL_EMBEDDING_TESTS=1 EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run pytest -q -m external_embedding

test-external-reranker:
	RUN_EXTERNAL_RERANKER_TESTS=1 RERANKER_BASE_URL=$(RERANKER_BASE_URL) $(UV) run pytest -q -m external_reranker

setup-local-llm:
	./infra/local_llm/setup_local_llm.sh

start-local-llm:
	./infra/local_llm/serve_local_llm.sh

stop-local-llm:
	$(UV) run python infra/local_llm/stop_local_llm.py

health-local-llm:
	./infra/local_llm/healthcheck.sh

qualify-local-llm:
	.venv-local-llm/bin/python infra/local_llm/qualify_local_llm.py

test-local-llm:
	RUN_EXTERNAL_LOCAL_LLM_TESTS=1 ./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run pytest -q -m external_local_llm

evaluate-local-extraction:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task extraction --split dev $(EVALUATION_OUTPUT_ARGS)

evaluate-local-query-builder:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task query-builder --split dev $(EVALUATION_OUTPUT_ARGS)

evaluate-local-grounding:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task grounding --split dev $(EVALUATION_OUTPUT_ARGS)

evaluate-local-llm-all:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task all --split dev $(EVALUATION_OUTPUT_ARGS)

smoke-local-llm-e2e:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/smoke_local_mlx_e2e.py --env-file $(ENV_FILE)

verify-poc-readiness:
	$(UV) run python scripts/verify_poc_readiness.py

require-limited-poc:
	$(UV) run python scripts/verify_poc_readiness.py --require-limited-poc

verify-scenario-poc:
	$(UV) run python evaluation/scenario_poc_hard_plastic_v1/validate.py
	$(UV) run python scripts/verify_scenario_poc.py

up-scenario-poc:
	VISION_PROVIDER=mock \
	VISION_MOCK_MODE=binary_candidate \
	VISION_TASK=ANY_DEFECT_CLASSIFICATION \
	VISION_ASSESSMENT_EXPECTED_THRESHOLD=0.8984375 \
	VISION_MODEL_ID=csight-e3-contract-mock \
	VISION_MODEL_VERSION=e3-epoch10-contract-v1 \
	$(COMPOSE_CMD) up --build --detach --wait --remove-orphans
	$(COMPOSE_CMD) run --rm migrator

up-e3-scenario-poc:
	VISION_PROVIDER=remote \
	VISION_BASE_URL=http://host.docker.internal:8093 \
	VISION_TASK=ANY_DEFECT_CLASSIFICATION \
	VISION_ASSESSMENT_EXPECTED_THRESHOLD=0.8984375 \
	VISION_MODEL_ID=csight-dinov2-vits14-kaputt-binary \
	VISION_MODEL_VERSION=e3-epoch10-20260827 \
	VISION_MODEL_REVISION=49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e \
	VISION_CONNECT_TIMEOUT_SECONDS=10 \
	VISION_READ_TIMEOUT_SECONDS=180 \
	VISION_TLS_VERIFY=false \
	$(COMPOSE_CMD) up --build --detach --wait --remove-orphans
	VISION_PROVIDER=remote \
	VISION_BASE_URL=http://host.docker.internal:8093 \
	VISION_TASK=ANY_DEFECT_CLASSIFICATION \
	VISION_ASSESSMENT_EXPECTED_THRESHOLD=0.8984375 \
	VISION_MODEL_ID=csight-dinov2-vits14-kaputt-binary \
	VISION_MODEL_VERSION=e3-epoch10-20260827 \
	VISION_MODEL_REVISION=49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e \
	VISION_CONNECT_TIMEOUT_SECONDS=10 \
	VISION_READ_TIMEOUT_SECONDS=180 \
	VISION_TLS_VERIFY=false \
	$(COMPOSE_CMD) run --rm migrator

seed-scenario-poc-demo:
	$(UV) run python scripts/seed_scenario_poc_demo.py --env-file $(ENV_FILE)

smoke-scenario-vision:
	$(UV) run python scripts/smoke_scenario_vision.py --env-file $(ENV_FILE)

smoke-e3-scenario-vision:
	$(UV) run python scripts/smoke_scenario_vision.py \
		--env-file $(ENV_FILE) \
		--timeout-seconds 180 \
		--allow-below-threshold \
		--expected-model-name csight-dinov2-vits14-kaputt-binary \
		--expected-model-version e3-epoch10-20260827 \
		--expected-model-revision 49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e \
		--verdict REAL_E3_CORE_INTEGRATION_PASS \
		--claim-boundary REAL_E3_CHECKPOINT_ON_SYNTHETIC_CONNECTIVITY_IMAGE_NOT_PRODUCT_QUALIFICATION

demo-scenario-poc: verify-scenario-poc up-scenario-poc seed-scenario-poc-demo smoke-scenario-vision

smoke-analysis:
	$(UV) run python scripts/smoke_analysis.py --env-file $(ENV_FILE)

build-policy-corpus:
	$(UV) run python scripts/build_policy_corpus.py

validate-policy-corpus:
	$(UV) run python scripts/validate_policy_corpus.py

build-evaluation-data:
	$(UV) run python scripts/build_evaluation_data.py

validate-evaluation-data:
	$(UV) run python scripts/validate_evaluation_data.py

evaluate-extraction-v2:
	$(UV) run python scripts/evaluate_llm_extraction_v2.py

evaluate-extraction-v2-qwen:
	$(UV) run python scripts/evaluate_extraction_v2_qwen.py \
		--env-file "$(QWEN4090_ENV_FILE)" --candidate-id "$(QWEN4090_CANDIDATE_ID)" --split dev

freeze-extraction-v2-qwen:
	$(UV) run python scripts/evaluate_extraction_v2_qwen.py \
		--candidate-id "$(QWEN4090_CANDIDATE_ID)" --split dev --freeze

evaluate-extraction-v2-qwen-test:
	$(UV) run python scripts/evaluate_extraction_v2_qwen.py \
		--env-file "$(QWEN4090_ENV_FILE)" --candidate-id "$(QWEN4090_CANDIDATE_ID)" \
		--split test --allow-sealed-test

verify-qwen4090-candidates:
	$(UV) run python scripts/verify_qwen4090_candidates.py

audit-qwen4090-hub:
	$(UV) run python scripts/audit_qwen4090_hub.py

verify-qwen4090-compose-profiles:
	$(UV) run python scripts/verify_qwen4090_compose_profiles.py

collect-qwen4090-host-evidence:
	$(UV) run python scripts/preflight_qwen4090_host.py \
		--candidate-id "$(QWEN4090_CANDIDATE_ID)" \
		--runtime-env "$(QWEN4090_RUNTIME_ENV_FILE)" --collect-unpinned

verify-qwen4090-host:
	$(UV) run python scripts/preflight_qwen4090_host.py \
		--candidate-id "$(QWEN4090_CANDIDATE_ID)" \
		--runtime-env "$(QWEN4090_RUNTIME_ENV_FILE)"

start-qwen4090-candidate:
	infra/llm/serve_qwen_candidate.sh \
		"$(QWEN4090_CANDIDATE_ID)" "$(QWEN4090_RUNTIME_ENV_FILE)"

stop-qwen4090-candidate:
	$(COMPOSE) --env-file "$(QWEN4090_RUNTIME_ENV_FILE)" \
		-f infra/llm/compose.llm.yml down --remove-orphans

require-qwen4090-release:
	$(UV) run python scripts/verify_qwen4090_candidates.py --require-eligible

build-query-builder-dataset:
	$(UV) run python scripts/build_query_builder_dataset.py

validate-query-builder-dataset:
	$(UV) run python scripts/validate_query_builder_dataset.py

evaluate-query-builder-raw:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy raw $(EVALUATION_OUTPUT_ARGS)

evaluate-query-builder-deterministic:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy deterministic $(EVALUATION_OUTPUT_ARGS)

evaluate-query-builder-llm:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy llm $(EVALUATION_OUTPUT_ARGS)

evaluate-query-builder:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy all $(EVALUATION_OUTPUT_ARGS)

smoke-policy-retrieval-run:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/smoke_policy_retrieval_run.py

evaluate-grounding-contract:
	$(UV) run python scripts/evaluate_grounding_contract.py

smoke-grounded-explanation:
	$(UV) run python scripts/smoke_grounded_explanation.py --env-file $(ENV_FILE)

report-reference-data:
	$(UV) run python scripts/generate_reference_reports.py

ingest-policy-corpus:
	$(UV) run python scripts/ingest_policy_corpus.py --env-file $(ENV_FILE)

validate-policy-db:
	$(UV) run python scripts/validate_policy_db.py --env-file $(ENV_FILE)

build-policy-rules:
	$(UV) run python scripts/build_policy_rule_sets.py

validate-policy-rules:
	$(UV) run python scripts/validate_policy_rule_sets.py

ingest-policy-rules:
	$(UV) run python scripts/ingest_policy_rules.py --env-file $(ENV_FILE)

validate-policy-rule-db:
	$(UV) run python scripts/validate_policy_rule_db.py --env-file $(ENV_FILE)

evaluate-policy-engine:
	$(UV) run python scripts/evaluate_policy_engine.py --split dev
	$(UV) run python scripts/verify_policy_engine_results.py

smoke-policy-evaluation:
	$(UV) run python scripts/smoke_policy_evaluation.py --env-file $(ENV_FILE)

build-human-review-evaluation:
	$(UV) run python scripts/build_human_review_evaluation.py

validate-human-review-evaluation:
	$(UV) run python scripts/validate_human_review_evaluation.py

evaluate-human-review-workflow:
	$(UV) run python scripts/evaluate_human_review_workflow.py --split dev
	$(UV) run python scripts/verify_human_review_results.py

smoke-human-review:
	$(UV) run python scripts/smoke_policy_evaluation.py --env-file $(ENV_FILE)
	$(UV) run python scripts/smoke_human_review.py --env-file $(ENV_FILE)

inspect-human-review-queue:
	$(UV) run python scripts/inspect_human_review_queue.py --env-file $(ENV_FILE)

start-embedding:
	@test ! -f $(EMBEDDING_PID_FILE) || ! kill -0 $$(cat $(EMBEDDING_PID_FILE)) 2>/dev/null || { echo "Embedding service already running"; exit 1; }
	@nohup env EMBEDDING_PORT=$(EMBEDDING_PORT) .venv-embedding/bin/uvicorn infra.embedding.server:app --host 127.0.0.1 --port $(EMBEDDING_PORT) --no-access-log > .embedding-service.log 2>&1 & echo $$! > $(EMBEDDING_PID_FILE)

stop-embedding:
	@if ! test -f $(EMBEDDING_PID_FILE); then echo "No Make-managed embedding service"; else pid=$$(cat $(EMBEDDING_PID_FILE)); case "$$pid" in ''|*[!0-9]*) echo "Invalid embedding PID file"; exit 1;; esac; if kill -0 $$pid 2>/dev/null; then kill $$pid; fi; rm -f $(EMBEDDING_PID_FILE); fi

health-embedding:
	@curl --fail --silent $(EMBEDDING_BASE_URL)/health
	@curl --fail --silent $(EMBEDDING_BASE_URL)/v1/models

build-policy-embeddings:
	$(UV) run python scripts/build_policy_embeddings.py --env-file $(ENV_FILE) --embedding-base-url $(EMBEDDING_BASE_URL)

prepare-csight-policy-runtime:
	$(UV) run python scripts/prepare_csight_synthetic_policy_runtime.py \
		--env-file "$(ENV_FILE)" \
		--embedding-base-url "$(EMBEDDING_BASE_URL)" \
		--output-root "$(CSIGHT_POLICY_OUTPUT)"

activate-policy-index:
	$(UV) run python scripts/activate_policy_index.py --env-file $(ENV_FILE) --tenant $(POLICY_TENANT) --index-version $(POLICY_INDEX_VERSION)

list-policy-indexes:
	$(UV) run python scripts/list_policy_indexes.py --env-file $(ENV_FILE)

seed-policy-identities:
	$(UV) run python scripts/seed_policy_demo_identities.py --env-file $(ENV_FILE)

evaluate-policy-lexical:
	$(UV) run python scripts/verify_policy_retrieval_results.py --mode lexical

evaluate-policy-dense:
	$(UV) run python scripts/verify_policy_retrieval_results.py --mode dense

evaluate-policy-hybrid:
	$(UV) run python scripts/verify_policy_retrieval_results.py --mode hybrid

evaluate-policy-retrieval:
	$(UV) run python scripts/verify_policy_retrieval_results.py --mode all

smoke-policy-search:
	$(UV) run python scripts/smoke_policy_search.py

analyze-policy-candidates:
	$(UV) run python scripts/analyze_policy_candidates.py --split dev --embedding-base-url $(EMBEDDING_BASE_URL)
	$(UV) run python scripts/analyze_policy_candidates.py --split test --embedding-base-url $(EMBEDDING_BASE_URL)

evaluate-policy-candidate-upper-bound: analyze-policy-candidates

start-reranker:
	@test ! -f $(RERANKER_PID_FILE) || ! kill -0 $$(cat $(RERANKER_PID_FILE)) 2>/dev/null || { echo "Reranker service already running"; exit 1; }
	@nohup env RERANKER_PORT=$(RERANKER_PORT) .venv-reranker/bin/uvicorn infra.reranker.server:app --host 127.0.0.1 --port $(RERANKER_PORT) --no-access-log > .reranker-service.log 2>&1 & echo $$! > $(RERANKER_PID_FILE)

stop-reranker:
	@if ! test -f $(RERANKER_PID_FILE); then echo "No Make-managed reranker service"; else pid=$$(cat $(RERANKER_PID_FILE)); case "$$pid" in ''|*[!0-9]*) echo "Invalid reranker PID file"; exit 1;; esac; if kill -0 $$pid 2>/dev/null; then kill $$pid; fi; rm -f $(RERANKER_PID_FILE); fi

health-reranker:
	@curl --fail --silent $(RERANKER_BASE_URL)/health
	@curl --fail --silent $(RERANKER_BASE_URL)/v1/models

qualify-policy-reranker:
	.venv-reranker/bin/python -m infra.reranker.qualify_reranker --base-url $(RERANKER_BASE_URL) --model-download-seconds $(RERANKER_DOWNLOAD_SECONDS) --cached-cold-load-seconds $(RERANKER_COLD_LOAD_SECONDS)

activate-policy-reranker-profile:
	$(UV) run python scripts/activate_policy_reranker_profile.py --env-file $(ENV_FILE)

evaluate-policy-reranker-dev:
	$(UV) run python scripts/evaluate_policy_reranker.py --split dev --reranker-base-url $(RERANKER_BASE_URL)

evaluate-policy-reranker-test:
	$(UV) run python scripts/evaluate_policy_reranker.py --split test --reranker-base-url $(RERANKER_BASE_URL)

smoke-policy-reranked-search:
	$(UV) run python scripts/smoke_policy_reranked_search.py
