SHELL := /bin/sh

UV ?= uv
COMPOSE ?= docker compose
COMPOSE_FILE := infra/compose.core.yml
ENV_FILE ?= .env
COMPOSE_CMD := $(COMPOSE) --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

.DEFAULT_GOAL := help

.PHONY: help up down logs migrate seed outbox lint format-check typecheck test test-integration test-all test-analysis test-analysis-integration test-external-llm test-external-vision smoke-analysis

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
	$(UV) run ruff format --check app tests alembic scripts

typecheck:
	$(UV) run pyright

test:
	$(UV) run pytest -q -m "not integration and not external_gpu and not external_vision"

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

smoke-analysis:
	$(UV) run python scripts/smoke_analysis.py --env-file $(ENV_FILE)
