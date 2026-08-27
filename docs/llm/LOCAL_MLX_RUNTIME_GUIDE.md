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
