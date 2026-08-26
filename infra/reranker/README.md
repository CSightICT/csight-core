# Private Qwen3 reranker service

This host-native service loads the pinned `Qwen/Qwen3-Reranker-0.6B` artifact and exposes
`GET /health`, `GET /v1/models`, and `POST /v1/rerank`. Bind it to `127.0.0.1:8092`; Docker
Core reaches it through `host.docker.internal`. It has no Core database credentials and receives
only candidate IDs and serialized clause passages after Core applies tenant, status, effective-date,
and allowlisted metadata filters.

The service follows the official Transformers example: left padding, fixed chat prefix/suffix,
`longest_first` tokenization, and normalization over the `no`/`yes` next-token logits. The returned
number is a pairwise relevance score in `[0, 1]`; it is not a calibrated probability and is never a
policy applicability, approval, legal-suitability, or business-decision score.

Use the isolated `.venv-reranker`. Access logs must remain disabled and request bodies/model inputs
must not be persisted or logged.
