# CSight host-native embedding service

This private service isolates Qwen3 embedding dependencies from the Core backend. It has no
database configuration or database access, does not log request bodies, and exposes only health,
model identity, and embedding endpoints. The pinned model revision is
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`.

Create `.venv-embedding` with `uv venv --python 3.12 .venv-embedding`, install the pinned
`requirements.txt`, then use the repository Make targets. Bind to loopback by default. A Docker
Core process may require a host-only/private bind reachable through `host.docker.internal`; never
publish this service to a public interface.
