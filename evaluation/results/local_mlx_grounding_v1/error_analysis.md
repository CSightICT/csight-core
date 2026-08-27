# Local MLX grounding error analysis

- Candidate `1.1.0-local.1` was structurally safe but placed every supported fact in unresolved conditions: citation recall, required fact coverage, and unresolved recall were all 0.
- Candidate `1.1.0-local.2` requires at least one supported statement during constrained generation and explicitly separates supported facts from unresolved review needs.
- Final Dev40/Test10 and Injection Dev20/Test10 had no structural, citation, decision, injection, reasoning, or replay errors.
- The actual E2E top-10 Citation Pack exceeded the local 4096-token context and was rejected; top-3 succeeded 10/10. No truncation or output repair was used.
