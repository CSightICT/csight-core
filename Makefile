SHELL := /bin/sh

UV ?= uv
COMPOSE ?= docker compose
COMPOSE_FILE := infra/compose.core.yml
ENV_FILE ?= .env
COMPOSE_CMD := $(COMPOSE) --env-file $(ENV_FILE) -f $(COMPOSE_FILE)
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

.DEFAULT_GOAL := help

.PHONY: help up down logs migrate seed outbox lint format-check typecheck test test-integration test-all test-analysis test-analysis-integration test-external-llm test-external-vision test-external-embedding test-external-reranker test-local-llm smoke-analysis build-policy-corpus validate-policy-corpus build-evaluation-data validate-evaluation-data evaluate-extraction-v2 evaluate-extraction-v2-qwen report-reference-data ingest-policy-corpus validate-policy-db start-embedding stop-embedding health-embedding build-policy-embeddings activate-policy-index list-policy-indexes seed-policy-identities evaluate-policy-lexical evaluate-policy-dense evaluate-policy-hybrid evaluate-policy-retrieval smoke-policy-search analyze-policy-candidates evaluate-policy-candidate-upper-bound start-reranker stop-reranker health-reranker qualify-policy-reranker activate-policy-reranker-profile evaluate-policy-reranker-dev evaluate-policy-reranker-test smoke-policy-reranked-search build-query-builder-dataset validate-query-builder-dataset evaluate-query-builder-raw evaluate-query-builder-deterministic evaluate-query-builder-llm evaluate-query-builder smoke-policy-retrieval-run evaluate-grounding-contract smoke-grounded-explanation setup-local-llm start-local-llm stop-local-llm health-local-llm qualify-local-llm evaluate-local-extraction evaluate-local-query-builder evaluate-local-grounding evaluate-local-llm-all smoke-local-llm-e2e

help:
	@echo "CSight Core commands"
	@echo "  make up            Build and start the core environment"
	@echo "  make down          Stop the core environment (preserves volumes)"
	@echo "  make logs          Follow core service logs"
	@echo "  make migrate       Apply Alembic migrations in the app image"
	@echo "  make seed          Explicitly seed local/test identities after migration"
	@echo "  make outbox        Dispatch one batch of pending analysis events"
	@echo "  make lint          Run Ruff lint checks"
	@echo "  make format-check  Check Ruff formatting"
	@echo "  make typecheck     Run Pyright"
	@echo "  make test          Run CI-safe tests (no local infra or external GPU)"
	@echo "  make test-integration  Run integration tests against the core environment"
	@echo "  make test-all      Run CI-safe and core integration tests"
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
	@echo "  make evaluate-extraction-v2-qwen  Run or explicitly skip real Qwen v2 qualification"
	@echo "  make build-query-builder-dataset / validate-query-builder-dataset"
	@echo "  make evaluate-query-builder  Compare frozen-HYBRID query strategies"
	@echo "  make evaluate-grounding-contract  Qualify deterministic citation guardrails"
	@echo "  make smoke-grounded-explanation  Run authenticated Mock grounding smoke"
	@echo "  make report-reference-data  Generate aggregate JSON and Markdown quality reports"
	@echo "  make ingest-policy-corpus  Explicitly ingest the validated synthetic corpus"
	@echo "  make validate-policy-db  Verify corpus, embedding, and active-index invariants"
	@echo "  make start-embedding  Start the private host-native Qwen embedding service"
	@echo "  make stop-embedding  Stop the private embedding service started by Make"
	@echo "  make health-embedding  Probe embedding health and pinned model metadata"
	@echo "  make build-policy-embeddings  Build/reuse embeddings and activate complete indexes"
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

up:
	$(COMPOSE_CMD) up --build --detach --wait

down:
	$(COMPOSE_CMD) down --remove-orphans

logs:
	$(COMPOSE_CMD) logs --follow --tail=200

migrate:
	$(COMPOSE_CMD) run --rm api uv run alembic upgrade head

seed:
	$(UV) run python -m app.bootstrap.seed --env-file $(ENV_FILE)

outbox:
	$(COMPOSE_CMD) run --rm dispatcher uv run python -m app.interface.dispatchers.outbox --once

lint:
	$(UV) run ruff check .

format-check:
	$(UV) run ruff format --check app tests alembic scripts infra

typecheck:
	$(UV) run pyright

test:
	$(UV) run pytest -q -m "not integration and not external_gpu and not external_vision and not external_embedding and not external_reranker and not external_local_llm"

test-integration:
	RUN_CORE_INTEGRATION=1 $(UV) run pytest -q -m integration

test-all: test test-integration

test-analysis:
	$(UV) run pytest -q -m "not integration and not external_gpu" -k "analysis or outbox or vllm or text_extraction"

test-analysis-integration:
	RUN_CORE_INTEGRATION=1 $(UV) run pytest -q -m integration -k "analysis or outbox or vllm or text_extraction"

test-external-llm:
	RUN_EXTERNAL_GPU_TESTS=1 $(UV) run pytest -q -m external_gpu

test-external-vision:
	RUN_EXTERNAL_VISION_TESTS=1 $(UV) run pytest -q -m external_vision

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
		$(UV) run python scripts/evaluate_local_mlx.py --task extraction --split dev

evaluate-local-query-builder:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task query-builder --split dev

evaluate-local-grounding:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task grounding --split dev

evaluate-local-llm-all:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/evaluate_local_mlx.py --task all --split dev

smoke-local-llm-e2e:
	./infra/local_llm/run_backend_with_local_llm.sh \
		$(UV) run python scripts/smoke_local_mlx_e2e.py --env-file $(ENV_FILE)

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
	$(UV) run python scripts/evaluate_extraction_v2_qwen.py

build-query-builder-dataset:
	$(UV) run python scripts/build_query_builder_dataset.py

validate-query-builder-dataset:
	$(UV) run python scripts/validate_query_builder_dataset.py

evaluate-query-builder-raw:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy raw

evaluate-query-builder-deterministic:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy deterministic

evaluate-query-builder-llm:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy llm

evaluate-query-builder:
	EMBEDDING_BASE_URL=$(EMBEDDING_BASE_URL) $(UV) run python scripts/evaluate_policy_query_builder.py --strategy all

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
