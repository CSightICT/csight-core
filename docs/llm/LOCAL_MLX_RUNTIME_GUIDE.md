# Local MLX runtime guide

Use the isolated `.venv-local-llm`; it is intentionally not part of backend dependencies.

```bash
make setup-local-llm
make start-local-llm
make health-local-llm
make qualify-local-llm
make test-local-llm
```

The server binds only `127.0.0.1:8080`. Docker services use `http://host.docker.internal:8080/v1`; host tools use `http://127.0.0.1:8080/v1`. `make start-local-llm` is a foreground process and should remain open. Stop only the PID recorded by the runtime tooling.

Known MLX-VLM constraints: `jinja2` must be installed, JSON Schema `uniqueItems` is unsupported, all object properties are made required, and the actual E2E uses top-3 citations to fit 4096 tokens. Core readiness never probes the optional LLM.

## Dev diagnostics after 2026-09-09

The legacy MLX evaluator is now Dev-only and requires a new private output directory, for example:

```sh
make evaluate-local-query-builder EVALUATION_OUTPUT_DIR=local-data/mlx-query-dev-unique-run
```

The parent must exist; an existing run directory is refused, even if empty. `--freeze`, `--split test`
and `--allow-sealed-test` are blocked before provider or dataset access. Historical result files are
not modified. This applies to all four `evaluate-local-*` targets. Explicitly running them still calls
the configured MLX/search services; the current change was verified with mocks, without starting them.

New schema `local_mlx_dev_evaluation/2.0.0` reports are non-release-eligible and unfrozen; raw
predictions/quotes/errors are not persisted. Retrieval HitRate, true clause Recall and complete Gold
coverage are separate. Unmeasured safety fields are null/NOT_RUN. A failed run directory is retained;
inspect the failure and use a different new path, never delete historical evidence to retry.
The separate candidate qualification harness and its authorization are unchanged. See
[ADR-0127](../../CSight_project_docs/docs/adr/0127-explicit-retrieval-diagnostics-and-legacy-dev-only-evaluation.md).
