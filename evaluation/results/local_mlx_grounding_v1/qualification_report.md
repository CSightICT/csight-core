# Local MLX grounding qualification

Result: `LOCAL_GROUNDING_POC_QUALIFIED_WITH_LIMITATIONS`.

Dev40 and sealed Test10 achieved 100% schema validity, citation validity/precision/recall, required-fact coverage, unresolved-condition recall, and deterministic replay. Injection Dev20/Test10 achieved 100% schema validity and zero prompt-injection, forbidden-field, or reasoning leakage.

Qualification is limited to the synthetic corpus, frozen prompt `1.1.0-local.2`, and a context-budgeted Citation Pack. It is not a production-model claim.
