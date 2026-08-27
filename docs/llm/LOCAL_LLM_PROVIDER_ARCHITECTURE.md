# Local LLM provider architecture

`LLMProvider` remains the only application-facing port. Mock, vLLM, and MLX are separate adapters selected in the composition root. MLX packages run only in a native macOS service; the backend talks to its OpenAI-compatible HTTP endpoint and never imports MLX.

Provider-specific prompt selection is confined to bootstrap composition. Domain/application code contains no MLX business rules. Provider errors fail closed and are never silently routed to Mock. Persisted metadata identifies provider `mlx`, served name `csight-qwen3.5-9b-local-poc`, prompt/profile hashes, model version, and immutable revision; it never stores the host cache path, raw prompt, raw response, or reasoning.
