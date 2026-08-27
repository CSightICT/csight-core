# CSight Local MLX runtime

This directory owns the host-native Local PoC runtime only. It has no Core database access and is
not installed into the backend environment or Docker image.

Run `make setup-local-llm`, then run `make start-local-llm` in a dedicated foreground terminal.
The server binds to `127.0.0.1:8080`, uses the pinned Qwen3.5 MLX snapshot, disables thinking by
default, caps context at 4096 tokens, and accepts one sequence at a time. A Docker Worker reaches it
at `http://host.docker.internal:8080/v1`.

Use `make health-local-llm` and `make qualify-local-llm` from another terminal. `make stop-local-llm`
only signals the PID recorded by this launcher and refuses to stop another process.
