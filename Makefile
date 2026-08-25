SHELL := /bin/sh

UV ?= uv
COMPOSE ?= docker compose
COMPOSE_FILE := infra/compose.core.yml
ENV_FILE ?= .env
COMPOSE_CMD := $(COMPOSE) --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

.DEFAULT_GOAL := help

.PHONY: help up down logs migrate lint format-check typecheck test test-integration test-all

help:
	@echo "CSight Sprint 0 commands"
	@echo "  make up            Build and start the core environment"
	@echo "  make down          Stop the core environment (preserves volumes)"
	@echo "  make logs          Follow core service logs"
	@echo "  make migrate       Apply Alembic migrations in the app image"
	@echo "  make lint          Run Ruff lint checks"
	@echo "  make format-check  Check Ruff formatting"
	@echo "  make typecheck     Run Pyright"
	@echo "  make test          Run CI-safe tests (no local infra or external GPU)"
	@echo "  make test-integration  Run integration tests against the core environment"
	@echo "  make test-all      Run CI-safe and core integration tests"

up:
	$(COMPOSE_CMD) up --build --detach --wait

down:
	$(COMPOSE_CMD) down --remove-orphans

logs:
	$(COMPOSE_CMD) logs --follow --tail=200

migrate:
	$(COMPOSE_CMD) run --rm api uv run alembic upgrade head

lint:
	$(UV) run ruff check .

format-check:
	$(UV) run ruff format --check .

typecheck:
	$(UV) run pyright

test:
	$(UV) run pytest -q -m "not integration and not external_gpu"

test-integration:
	RUN_CORE_INTEGRATION=1 $(UV) run pytest -q -m integration

test-all: test test-integration
