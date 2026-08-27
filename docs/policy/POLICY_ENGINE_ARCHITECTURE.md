# Policy Engine Architecture

## Boundary

```text
Policy Retrieval -> relevant clauses
Grounded Explanation -> reviewer-facing clause explanation
Structured Policy Engine -> deterministic curated rule execution
Human Review -> final business decision
```

The engine never consumes grounded explanation text, retrieval rank, raw prompts, or provider
responses. `app/platform/policy_engine` contains only strict types and pure evaluation functions.
Application use cases depend on a repository port; SQLAlchemy, FastAPI, RabbitMQ, and Celery remain
in adapters and interfaces.

## Runtime

`POST` atomically creates an append-only run, hashed input snapshot, and identifier-only outbox
event. The dispatcher publishes five opaque IDs. A thin worker reloads the frozen snapshot and
immutable rule set, verifies both hashes, evaluates without an external model, and appends rule,
condition, and effect rows. A duplicate delivery cannot claim a terminal run and returns `NOOP`.

## Trust boundary

Case-declared and allowlisted typed metadata are hard inputs. Local LLM issue types and claim count
are advisory and force review. Local extracted action/ambiguity fields are excluded. Mock Vision
defect conditions return `NOT_EVALUATED`; Alignment remains unqualified and unavailable.
