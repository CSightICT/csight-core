# CSight coding-agent instructions

The canonical project rules are maintained in
[`CSight_project_docs/AGENTS.md`](CSight_project_docs/AGENTS.md). Read that file,
the relevant design documents, and all accepted ADRs before changing code.

At the start of every task, also read
[`docs/progress/CURRENT_STATUS.md`](docs/progress/CURRENT_STATUS.md). Before ending
a task, update its handoff checklist, actual verification results, unresolved
items, next action, and append-only session log.

In particular:

- Keep `app/platform` and `app/domains` independent from FastAPI, SQLAlchemy,
  Celery, HTTPX, MinIO, and model-provider SDKs.
- Connect external technology through ports and adapters.
- Keep Celery tasks as thin application-use-case entry points.
- Models analyze evidence; versioned policy and human review own final decisions.
- Preserve analysis runs append-only and record model, prompt, policy, threshold,
  embedding, and retrieval-index versions when those features are introduced.
- Do not call external GPU services in the default test suite.
- Include migrations, tests, type checks, and documentation with behavior changes.
